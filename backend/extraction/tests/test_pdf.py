from dataclasses import replace
import logging
import sys
import time

import pytest

from backend.extraction import PdfLimits, PdfOutcome, extract_pdf
from backend.extraction.pdf import _parse_pdf
from fixtures import STUDY_TEXT, make_pdf, text_stream


LINUX = pytest.mark.skipif(sys.platform != "linux", reason="Hard address-space limits require Linux.")


def parse(data: bytes, limits: PdfLimits = PdfLimits()):
    # Only trusted synthetic fixtures use this internal call on developer macOS.
    # Every ordinary fixture also exercises the production process boundary on Linux.
    return extract_pdf(data, limits) if sys.platform == "linux" else _parse_pdf(data, limits)


def test_deterministic_order_and_one_based_page_references():
    first = STUDY_TEXT + " First page ends here."
    second = "Second page starts here. " + STUDY_TEXT
    data = make_pdf(first, "", second, compressed=True)
    assert data == make_pdf(first, "", second, compressed=True)
    result = parse(data)
    assert result.outcome == PdfOutcome.OK
    assert result.reason is None
    assert result.version == "pdf-native-1"
    assert result.page_count == 3
    assert [(page.page_number, page.text) for page in result.pages] == [
        (1, first), (2, ""), (3, second),
    ]
    assert [page.sufficient for page in result.pages] == [True, False, True]
    assert result == parse(data)


def test_preserves_stream_order_and_normalizes_whitespace():
    top = "Top passage. " + STUDY_TEXT
    bottom = "Bottom passage. " + STUDY_TEXT
    raw = text_stream(top) + text_stream(bottom).replace(b"700 Td", b"650 Td")
    result = parse(make_pdf("", raw_stream=raw))
    assert result.outcome == PdfOutcome.OK
    assert result.pages[0].text == top + "\n" + bottom
    spaced = parse(make_pdf("  Plants   convert\t sunlight.  " + STUDY_TEXT))
    assert spaced.pages[0].text == "Plants convert sunlight. " + STUDY_TEXT


@pytest.mark.parametrize("length,outcome", [(79, PdfOutcome.INSUFFICIENT_TEXT), (80, PdfOutcome.OK)])
def test_exact_minimum_native_characters(length, outcome):
    result = parse(make_pdf("a" * length))
    assert result.outcome == outcome
    assert result.pages[0].text == "a" * length
    assert result.pages[0].alphanumeric_characters == length
    assert result.pages[0].sufficient == (length == 80)


@pytest.mark.parametrize("punctuation,outcome", [(53, PdfOutcome.OK), (54, PdfOutcome.INSUFFICIENT_TEXT)])
def test_character_density_rejects_punctuation_heavy_text(punctuation, outcome):
    text = "a" * 80 + "!" * punctuation
    result = parse(make_pdf(text))
    assert result.outcome == outcome
    assert result.pages[0].text == text
    assert result.pages[0].alphanumeric_characters == 80


@pytest.mark.parametrize("invalid,outcome", [(2, PdfOutcome.OK), (3, PdfOutcome.INSUFFICIENT_TEXT)])
def test_replacement_character_threshold_with_actual_font_mapping(invalid, outcome):
    result = parse(make_pdf("a" * 100 + "\x7f" * invalid, replacement_font=True))
    assert result.outcome == outcome
    assert result.pages[0].text == "a" * 100 + "\ufffd" * invalid


@pytest.mark.parametrize("text", ["", "     ", "!!!", "Page 1", "1234567890"])
def test_empty_and_short_native_content_is_not_success(text):
    result = parse(make_pdf(text))
    assert result.outcome == PdfOutcome.INSUFFICIENT_TEXT
    assert result.reason == "native_text_threshold"
    assert not result.pages[0].sufficient


@pytest.mark.parametrize("options", [
    {"image_pages": (1,)},
    {"image_pages": (1,), "form_image": True},
    {"inline_image": True},
])
def test_image_only_including_form_and_inline_images(options):
    result = parse(make_pdf("", **options))
    assert result.outcome == PdfOutcome.IMAGE_ONLY
    assert result.reason == "no_native_text"
    assert result.pages[0].has_image
    assert result.pages[0].text == ""


def test_unused_image_resource_does_not_make_blank_page_a_scan():
    result = parse(make_pdf("", unused_image=True))
    assert result.outcome == PdfOutcome.INSUFFICIENT_TEXT
    assert not result.pages[0].has_image


def test_vector_only_page_is_not_silently_treated_as_blank():
    data = make_pdf(STUDY_TEXT, "")
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    import io

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    vector = DecodedStreamObject()
    vector.set_data(b"0 0 100 100 re f\n")
    writer.pages[1][NameObject("/Contents")] = writer._add_object(vector)
    output = io.BytesIO()
    writer.write(output)
    result = parse(output.getvalue())
    assert result.outcome == PdfOutcome.INSUFFICIENT_TEXT
    assert result.reason == "partial_native_text"
    assert result.pages[1].has_graphics
    assert not result.pages[1].has_image
    assert result.pages[1].text == ""


def test_parser_warning_cannot_turn_repaired_content_into_success():
    # Even strict pypdf emits a warning and substitutes missing font resources.
    import io
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf(STUDY_TEXT))))
    writer.pages[0]["/Resources"][NameObject("/Font")] = NumberObject(1)
    output = io.BytesIO()
    writer.write(output)
    result = parse(output.getvalue())
    assert result.outcome == PdfOutcome.CORRUPT
    assert result.reason == "parser_warning"
    assert result.pages == ()


@pytest.mark.parametrize("second,images", [("", (2,)), ("Page 2", (2,)), ("short", ())])
def test_partial_document_cannot_silently_skip_insufficient_pages(second, images):
    result = parse(make_pdf(STUDY_TEXT, second, image_pages=images))
    assert result.outcome == PdfOutcome.INSUFFICIENT_TEXT
    assert result.reason == "partial_native_text"
    assert result.page_count == 2
    assert result.pages[0].sufficient
    assert not result.pages[1].sufficient
    assert result.pages[1].text == second
    assert result.pages[1].has_image == bool(images)


@pytest.mark.parametrize("password", ["synthetic-password", ""])
@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-128", "AES-256"])
def test_encrypted_even_with_empty_password_is_explicit(password, algorithm):
    result = parse(make_pdf(STUDY_TEXT, password=password, encryption_algorithm=algorithm))
    assert result.outcome == PdfOutcome.ENCRYPTED
    assert result.reason == "password_protected"
    assert result.pages == ()


@LINUX
def test_aes_encryption_identified_without_optional_crypto_provider(tmp_path, monkeypatch):
    import shutil
    import sysconfig
    import venv
    import pypdf
    from backend.extraction import pdf

    # Construct genuine AES bytes with the test-only provider, but deliberately
    # launch the actual parser in a clean venv containing only the runtime dependency.
    data = make_pdf(STUDY_TEXT, password="", encryption_algorithm="AES-256")
    directory = tmp_path / "parser-only"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(directory)
    site_packages = directory / "lib" / f"python{sysconfig.get_python_version()}" / "site-packages"
    shutil.copytree(pypdf.__path__[0], site_packages / "pypdf")
    monkeypatch.setattr(pdf.sys, "executable", str(directory / "bin" / "python"))
    result = extract_pdf(data)
    assert result.outcome == PdfOutcome.ENCRYPTED
    assert result.reason == "password_protected"
    assert result.pages == ()


def test_external_image_decoder_is_disabled_even_if_configured():
    import io
    from pypdf import PdfReader, PdfWriter, apply_configuration, get_configuration
    from pypdf.generic import NameObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf("", raw_stream=b"fake-jbig2"))))
    writer.pages[0]["/Contents"][NameObject("/Filter")] = NameObject("/JBIG2Decode")
    output = io.BytesIO()
    writer.write(output)
    with apply_configuration(jbig2dec_binary="/bin/false", disable_legacy_handling=True):
        result = _parse_pdf(output.getvalue(), PdfLimits())
        assert get_configuration().jbig2dec_binary == "/bin/false"
    assert result.outcome == PdfOutcome.UNSUPPORTED
    assert result.reason == "native_feature"
    assert result.pages == ()


@pytest.mark.parametrize("data", [
    b"%PDF-1.7\nbroken\n%%EOF\n",
    make_pdf(STUDY_TEXT)[:-30],
    make_pdf("", raw_stream=b"/Missing Do\n"),
])
def test_corrupt_pdf_does_not_return_partial_success(data):
    result = parse(data)
    assert result.outcome == PdfOutcome.CORRUPT
    assert result.reason == "invalid_pdf"
    assert result.pages == ()
    assert result.page_count == 0


@pytest.mark.parametrize("data", [b"", b"not a PDF", b"PK\x03\x04"])
def test_public_entry_rejects_non_pdf(data):
    result = extract_pdf(data)
    assert result.outcome == PdfOutcome.UNSUPPORTED
    assert result.reason == "pdf_header"
    assert result.pages == ()


def test_page_limit_at_and_beyond_boundary():
    limits = replace(PdfLimits(), max_pages=2)
    assert parse(make_pdf(STUDY_TEXT, STUDY_TEXT), limits).page_count == 2
    result = parse(make_pdf(STUDY_TEXT, STUDY_TEXT, STUDY_TEXT), limits)
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "page_count"
    assert result.pages == ()


def test_input_byte_limit_at_and_beyond_boundary():
    data = make_pdf(STUDY_TEXT)
    limits = replace(PdfLimits(), max_input_bytes=len(data))
    if sys.platform == "linux":
        assert extract_pdf(data, limits).outcome == PdfOutcome.OK
    result = extract_pdf(data + b"\n", limits)
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "input_bytes"


def test_decoded_stream_limits_include_compressed_bytes_and_total():
    stream = text_stream(STUDY_TEXT)
    data = make_pdf(STUDY_TEXT, compressed=True)
    limits = replace(PdfLimits(), max_decoded_stream_bytes=len(stream))
    assert parse(data, limits).outcome == PdfOutcome.OK
    result = parse(data, replace(limits, max_decoded_stream_bytes=len(stream) - 1))
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "decoded_stream_bytes"
    total = replace(PdfLimits(), max_total_decoded_stream_bytes=2 * len(stream))
    assert parse(make_pdf(STUDY_TEXT, STUDY_TEXT, compressed=True), total).outcome == PdfOutcome.OK
    result = parse(make_pdf(STUDY_TEXT, STUDY_TEXT, compressed=True),
                   replace(total, max_total_decoded_stream_bytes=2 * len(stream) - 1))
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "total_decoded_stream_bytes"


def test_nested_form_streams_are_counted_before_extraction():
    result = parse(make_pdf("", form_depth=3),
                   replace(PdfLimits(), max_total_decoded_stream_bytes=20))
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "total_decoded_stream_bytes"


def test_form_depth_boundary():
    accepted = parse(make_pdf("", form_depth=31, form_fanout=1))
    assert accepted.outcome == PdfOutcome.INSUFFICIENT_TEXT
    result = parse(make_pdf("", form_depth=32, form_fanout=1))
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "form_depth"
    assert result.pages == ()


def test_output_character_limit_at_and_beyond_boundary():
    data = make_pdf(STUDY_TEXT, STUDY_TEXT)
    limits = replace(PdfLimits(), max_output_characters=2 * len(STUDY_TEXT))
    assert parse(data, limits).outcome == PdfOutcome.OK
    result = parse(data, replace(limits, max_output_characters=limits.max_output_characters - 1))
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "output_characters"
    assert result.pages == ()


@LINUX
def test_real_parser_cpu_limit_on_small_expanding_form_graph():
    data = make_pdf("", form_depth=24, compressed=True)
    assert len(data) < 20_000
    started = time.monotonic()
    result = extract_pdf(data, replace(PdfLimits(), cpu_seconds=1, wall_seconds=10))
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "cpu_seconds"
    assert result.pages == ()
    assert time.monotonic() - started < 5


@LINUX
def test_real_parser_wall_timeout_kills_and_reaps_process():
    data = make_pdf("", form_depth=24, compressed=True)
    started = time.monotonic()
    result = extract_pdf(data, replace(PdfLimits(), cpu_seconds=60, wall_seconds=1))
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "wall_seconds"
    assert result.pages == ()
    assert time.monotonic() - started < 4


@LINUX
def test_real_parser_memory_limit_on_compressed_expansion():
    # A tiny input expands beyond the child's address space while decoding,
    # before a decoded-length check could possibly run.
    data = make_pdf("", raw_stream=b"%" + b"x" * (96 * 1024 * 1024) + b"\n",
                    compressed=True)
    assert len(data) < 128 * 1024
    limits = replace(PdfLimits(), memory_bytes=80 * 1024 * 1024,
                     max_decoded_stream_bytes=128 * 1024 * 1024,
                     max_total_decoded_stream_bytes=128 * 1024 * 1024)
    result = extract_pdf(data, limits)
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason in {"memory_bytes", "process_memory_or_termination"}
    assert result.pages == ()
    assert extract_pdf(make_pdf(STUDY_TEXT)).outcome == PdfOutcome.OK


@LINUX
def test_native_parser_decompression_limit_is_an_explicit_resource_outcome():
    data = make_pdf("", raw_stream=b"%" + b"x" * 75_000_001 + b"\n", compressed=True)
    result = extract_pdf(data)
    assert result.outcome == PdfOutcome.RESOURCE_LIMIT
    assert result.reason == "native_parser_limit"
    assert result.pages == ()


def test_no_document_text_or_parser_diagnostics_in_public_logs(caplog):
    secret_marker = "SYNTHETIC_PRIVATE_MARKER"
    with caplog.at_level(logging.WARNING):
        result = extract_pdf(b"%PDF-1.7\n" + secret_marker.encode() + b"\n%%EOF\n")
    expected = PdfOutcome.CORRUPT if sys.platform == "linux" else PdfOutcome.ISOLATION_UNAVAILABLE
    assert result.outcome == expected
    assert secret_marker not in caplog.text
    assert "pdf_extraction:" in caplog.text


@pytest.mark.skipif(sys.platform == "linux", reason="Non-Linux fail-closed contract.")
def test_unsupported_platform_does_not_parse_untrusted_document():
    result = extract_pdf(make_pdf(STUDY_TEXT))
    assert result.outcome == PdfOutcome.ISOLATION_UNAVAILABLE
    assert result.reason == "linux_required"
    assert result.pages == ()


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_limits_raise_instead_of_silently_defaulting(value):
    with pytest.raises(ValueError, match="positive integers"):
        PdfLimits(cpu_seconds=value)


def test_mutable_input_is_rejected():
    with pytest.raises(TypeError, match="bytes"):
        extract_pdf(bytearray(b"%PDF-1.7"))
