from dataclasses import FrozenInstanceError

import pytest

from extraction import (
    TextLimits,
    TextOutcome,
    extract_markdown,
    extract_txt,
)


def test_txt_preserves_unicode_and_one_based_source_lines():
    result = extract_txt(
        b"\xef\xbb\xbfFirst line.\r\nCafe\xcc\x81 and \xf0\x9f\x8c\xb1.\r\n"
    )
    assert result.outcome == TextOutcome.OK
    assert result.source_format == "txt"
    assert result.version == "text-native-1"
    assert len(result.sections) == 1
    section = result.sections[0]
    assert section.headings == ()
    assert (section.line_start, section.line_end) == (1, 2)
    assert section.text == "First line.\nCaf\u00e9 and \U0001f331."
    with pytest.raises(FrozenInstanceError):
        section.text = "changed"


def test_txt_keeps_markdown_syntax_as_plain_text():
    result = extract_txt(b"# This stays plain text\n<script>literal</script>\n")
    assert result.outcome == TextOutcome.OK
    assert result.sections[0].headings == ()
    assert result.sections[0].text == "# This stays plain text\n<script>literal</script>"


def test_markdown_preserves_nested_headings_and_source_lines():
    result = extract_markdown(
        b"Intro line\n\n# Biology ##\nBody one\n\n## Cells\nBody two\n"
    )
    assert result.outcome == TextOutcome.OK
    assert [
        (section.headings, section.line_start, section.line_end, section.text)
        for section in result.sections
    ] == [
        ((), 1, 1, "Intro line"),
        (("Biology",), 3, 4, "Body one"),
        (("Biology", "Cells"), 6, 7, "Body two"),
    ]


def test_atx_heading_with_only_closing_hashes_has_an_empty_title():
    result = extract_markdown(b"# ###")
    assert result.outcome == TextOutcome.OK
    assert len(result.sections) == 1
    assert result.sections[0].headings == ("",)
    assert (result.sections[0].line_start, result.sections[0].line_end) == (1, 1)


def test_markdown_supports_setext_headings_and_literal_fenced_examples():
    result = extract_markdown(
        b"Topic\n=====\nText\n\n```md\n# not a heading\n```\n"
        b"Child\n-----\nMore"
    )
    assert result.outcome == TextOutcome.OK
    assert [
        (section.headings, section.line_start, section.line_end, section.text)
        for section in result.sections
    ] == [
        (
            ("Topic",),
            1,
            7,
            "Text\n\n```md\n# not a heading\n```",
        ),
        (("Topic", "Child"), 8, 10, "More"),
    ]


def test_consumed_setext_underline_is_not_reinterpreted_as_a_heading():
    exact = extract_markdown(
        b"Title\n---\n---",
        TextLimits(max_output_characters=8),
    )
    exceeded = extract_markdown(
        b"Title\n---\n---",
        TextLimits(max_output_characters=7),
    )
    assert exact.outcome == TextOutcome.OK
    assert [
        (section.headings, section.line_start, section.line_end, section.text)
        for section in exact.sections
    ] == [(("Title",), 1, 3, "---")]
    assert exceeded.outcome == TextOutcome.RESOURCE_LIMIT
    assert exceeded.reason == "output_characters"
    assert exceeded.sections == ()


def test_horizontal_rule_after_fenced_code_is_not_a_setext_heading():
    result = extract_markdown(b"# Topic\n```\ncode\n```\n---\nAfter")
    assert result.outcome == TextOutcome.OK
    assert len(result.sections) == 1
    assert result.sections[0].headings == ("Topic",)
    assert result.sections[0].text == "```\ncode\n```\n---\nAfter"


def test_markdown_content_is_returned_as_inert_text():
    source = b"# Example\n<script>not executed</script>\n[link](javascript:alert(1))"
    result = extract_markdown(source)
    assert result.outcome == TextOutcome.OK
    assert result.sections[0].text == (
        "<script>not executed</script>\n[link](javascript:alert(1))"
    )


@pytest.mark.parametrize("extract", [extract_txt, extract_markdown])
@pytest.mark.parametrize("data", [b"", b" \t\r\n"])
def test_empty_inputs_have_explicit_empty_outcome(extract, data):
    result = extract(data)
    assert result.outcome == TextOutcome.EMPTY
    assert result.reason == "empty_document"
    assert result.sections == ()


@pytest.mark.parametrize("extract", [extract_txt, extract_markdown])
def test_invalid_utf8_fails_without_partial_sections(extract):
    result = extract(b"# Heading\nValid prefix\n\xff")
    assert result.outcome == TextOutcome.INVALID_ENCODING
    assert result.reason == "invalid_utf8"
    assert result.sections == ()


def test_input_byte_limit_is_inclusive_and_never_truncates():
    exact = extract_txt(b"four", TextLimits(max_input_bytes=4))
    exceeded = extract_txt(b"fives", TextLimits(max_input_bytes=4))
    assert exact.outcome == TextOutcome.OK
    assert exact.sections[0].text == "four"
    assert exceeded.outcome == TextOutcome.RESOURCE_LIMIT
    assert exceeded.reason == "input_bytes"
    assert exceeded.sections == ()


def test_line_limit_is_inclusive():
    exact = extract_txt(b"a\nb", TextLimits(max_lines=2))
    exceeded = extract_txt(b"a\nb\nc", TextLimits(max_lines=2))
    assert exact.outcome == TextOutcome.OK
    assert exceeded.outcome == TextOutcome.RESOURCE_LIMIT
    assert exceeded.reason == "line_count"


def test_output_character_limit_is_inclusive_and_includes_heading_labels():
    exact = extract_markdown(b"# X\nab", TextLimits(max_output_characters=3))
    exceeded = extract_markdown(b"# X\nabc", TextLimits(max_output_characters=3))
    assert exact.outcome == TextOutcome.OK
    assert exceeded.outcome == TextOutcome.RESOURCE_LIMIT
    assert exceeded.reason == "output_characters"
    assert exceeded.sections == ()


def test_section_limit_is_enforced_without_partial_results():
    result = extract_markdown(b"# One\n# Two", TextLimits(max_sections=1))
    assert result.outcome == TextOutcome.RESOURCE_LIMIT
    assert result.reason == "section_count"
    assert result.sections == ()


def test_markdown_heading_only_input_preserves_heading():
    result = extract_markdown(b"# Heading")
    assert result.outcome == TextOutcome.OK
    assert result.sections[0].headings == ("Heading",)
    assert result.sections[0].text == ""
    assert (result.sections[0].line_start, result.sections[0].line_end) == (1, 1)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_limits_require_positive_non_boolean_integers(value):
    with pytest.raises(ValueError):
        TextLimits(max_lines=value)


@pytest.mark.parametrize("extract", [extract_txt, extract_markdown])
@pytest.mark.parametrize("data", ["text", bytearray(b"text"), None])
def test_input_must_be_bytes(extract, data):
    with pytest.raises(TypeError):
        extract(data)
