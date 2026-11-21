from dataclasses import asdict, dataclass
from enum import StrEnum
import io
import json
import logging
from pathlib import Path
import signal
import subprocess
import sys
import unicodedata


EXTRACTION_VERSION = "pdf-native-1"
MIN_ALPHANUMERIC_CHARACTERS = 80
MIN_ALPHANUMERIC_RATIO = 0.60
MAX_INVALID_CHARACTER_RATIO = 0.02


class PdfOutcome(StrEnum):
    OK = "ok"
    UNSUPPORTED = "unsupported"
    ENCRYPTED = "encrypted"
    CORRUPT = "corrupt"
    IMAGE_ONLY = "image_only"
    INSUFFICIENT_TEXT = "insufficient_text"
    RESOURCE_LIMIT = "resource_limit"
    ISOLATION_UNAVAILABLE = "isolation_unavailable"
    PARSER_UNAVAILABLE = "parser_unavailable"
    PARSER_FAILURE = "parser_failure"


@dataclass(frozen=True)
class PdfLimits:
    max_input_bytes: int = 16 * 1024 * 1024
    max_pages: int = 100
    max_decoded_stream_bytes: int = 8 * 1024 * 1024
    max_total_decoded_stream_bytes: int = 32 * 1024 * 1024
    max_output_characters: int = 1_000_000
    memory_bytes: int = 512 * 1024 * 1024
    cpu_seconds: int = 10
    wall_seconds: int = 15

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("PDF limits must be positive integers.")


@dataclass(frozen=True)
class PdfPage:
    page_number: int
    text: str
    alphanumeric_characters: int
    sufficient: bool
    has_image: bool
    has_graphics: bool


@dataclass(frozen=True)
class PdfExtraction:
    outcome: PdfOutcome
    pages: tuple[PdfPage, ...] = ()
    page_count: int = 0
    reason: str | None = None
    version: str = EXTRACTION_VERSION


def _failure(outcome: PdfOutcome, reason: str) -> PdfExtraction:
    logging.warning("pdf_extraction: %s (%s)", outcome.value, reason)
    return PdfExtraction(outcome, reason=reason)


def extract_pdf(data: bytes, limits: PdfLimits = PdfLimits()) -> PdfExtraction:
    """Extract untrusted bytes only in a resource-limited, disposable Linux process."""
    if not isinstance(data, bytes):
        raise TypeError("PDF input must be bytes.")
    if len(data) > limits.max_input_bytes:
        return _failure(PdfOutcome.RESOURCE_LIMIT, "input_bytes")
    if not data.startswith(b"%PDF-"):
        return _failure(PdfOutcome.UNSUPPORTED, "pdf_header")
    if sys.platform != "linux":
        return _failure(PdfOutcome.ISOLATION_UNAVAILABLE, "linux_required")

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(Path(__file__).resolve()),
                json.dumps(asdict(limits)),
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=limits.wall_seconds,
            check=False,
            # No credentials/configuration are inherited by the parser process.
            env={},
        )
    except subprocess.TimeoutExpired:
        return _failure(PdfOutcome.RESOURCE_LIMIT, "wall_seconds")
    except OSError:
        return _failure(PdfOutcome.ISOLATION_UNAVAILABLE, "process_start")

    if completed.returncode == -signal.SIGXCPU:
        return _failure(PdfOutcome.RESOURCE_LIMIT, "cpu_seconds")
    if completed.returncode in (-signal.SIGKILL, 20):
        return _failure(PdfOutcome.RESOURCE_LIMIT, "process_memory_or_termination")
    if completed.returncode != 0:
        return _failure(PdfOutcome.PARSER_FAILURE, "process_exit")

    try:
        payload = json.loads(completed.stdout)
        result = PdfExtraction(
            outcome=PdfOutcome(payload["outcome"]),
            pages=tuple(PdfPage(**page) for page in payload["pages"]),
            page_count=payload["page_count"],
            reason=payload["reason"],
            version=payload["version"],
        )
    except (ValueError, KeyError, TypeError):
        return _failure(PdfOutcome.PARSER_FAILURE, "invalid_result")
    if result.outcome != PdfOutcome.OK:
        logging.warning("pdf_extraction: %s (%s)", result.outcome.value, result.reason)
    return result


class _LimitExceeded(Exception):
    pass


class _EncryptedInput(Exception):
    pass


class _ParserWarnings(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.seen = False

    def emit(self, record: logging.LogRecord) -> None:
        # Detect parser repair/skipping without formatting or retaining source-bearing diagnostics.
        self.seen = True


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()


def _quality(text: str) -> tuple[int, bool]:
    visible = [character for character in text if not character.isspace()]
    meaningful = sum(character.isalnum() for character in visible)
    invalid = sum(
        character == "\ufffd" or unicodedata.category(character).startswith("C")
        for character in visible
    )
    sufficient = (
        meaningful >= MIN_ALPHANUMERIC_CHARACTERS
        and meaningful >= MIN_ALPHANUMERIC_RATIO * len(visible)
        and invalid <= MAX_INVALID_CHARACTER_RATIO * len(visible)
    )
    return meaningful, sufficient


def _parse_pdf(data: bytes, limits: PdfLimits) -> PdfExtraction:
    # Imported only after the child has installed OS limits; never parse in the caller.
    from pypdf import PdfReader, get_configuration, overwrite_configuration
    from pypdf.errors import DependencyError, LimitReachedError, PdfReadError, PyPdfError
    from pypdf.generic import ContentStream, DictionaryObject, PdfObject

    class NativeTextReader(PdfReader):
        def _handle_encryption(self, password: str | bytes | None) -> None:
            # The pinned parser otherwise attempts empty-password decryption here.
            # Abort on a parsed /Encrypt trailer, before crypto or any page access.
            raise _EncryptedInput

    decoded_bytes = 0

    def content_stream(stream: PdfObject | None, reader: PdfReader) -> ContentStream:
        nonlocal decoded_bytes
        content = ContentStream(stream, reader)
        size = len(content.get_data())
        decoded_bytes += size
        if size > limits.max_decoded_stream_bytes:
            raise _LimitExceeded("decoded_stream_bytes")
        if decoded_bytes > limits.max_total_decoded_stream_bytes:
            raise _LimitExceeded("total_decoded_stream_bytes")
        return content

    def dictionary(value: PdfObject) -> DictionaryObject:
        resolved = value.get_object()
        if not isinstance(resolved, DictionaryObject):
            raise PdfReadError("Invalid resource dictionary.")
        return resolved

    def painted_content(
        content: ContentStream,
        resources: DictionaryObject,
        reader: PdfReader,
        ancestors: tuple[int, ...] = (),
    ) -> tuple[bool, bool]:
        image, graphics = False, False
        for operands, operator in content.operations:
            if operator == b"INLINE IMAGE":
                image = True
            elif operator in (b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"sh"):
                graphics = True
            elif operator == b"Do":
                xobjects = dictionary(resources.get("/XObject", DictionaryObject()))
                target = xobjects[operands[0]].get_object()
                if not isinstance(target, DictionaryObject):
                    raise PdfReadError("Invalid XObject.")
                subtype = target.get("/Subtype")
                if subtype == "/Image":
                    image = True
                elif subtype == "/Form":
                    identity = id(target)
                    if identity in ancestors:
                        raise PdfReadError("Cyclic form.")
                    if len(ancestors) >= 32:
                        raise _LimitExceeded("form_depth")
                    nested = content_stream(target, reader)
                    nested_resources = dictionary(target.get("/Resources", resources))
                    nested_image, nested_graphics = painted_content(
                        nested, nested_resources, reader, (*ancestors, identity)
                    )
                    image = image or nested_image
                    graphics = graphics or nested_graphics
                else:
                    raise PdfReadError("Unsupported XObject subtype.")
        return image, graphics

    parser_logger = logging.getLogger("pypdf")
    monitor = _ParserWarnings()
    previous_level, previous_propagation = parser_logger.level, parser_logger.propagate
    parser_logger.setLevel(logging.WARNING)
    parser_logger.propagate = False
    parser_logger.addHandler(monitor)
    previous_configuration = get_configuration()
    # Native text never needs an external image decoder or its temporary files/processes.
    overwrite_configuration(jbig2dec_binary=None, disable_legacy_handling=True)
    try:
        reader = NativeTextReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            return PdfExtraction(PdfOutcome.ENCRYPTED, reason="password_protected")
        count = len(reader.pages)
        if count > limits.max_pages:
            raise _LimitExceeded("page_count")
        pages = []
        output_characters = 0
        for number, page in enumerate(reader.pages, start=1):
            content = content_stream(page.get("/Contents"), reader)
            resources = dictionary(page.get("/Resources", DictionaryObject()))
            has_image, has_graphics = painted_content(content, resources, reader)
            text = _normalize(page.extract_text(extraction_mode="plain"))
            output_characters += len(text)
            if output_characters > limits.max_output_characters:
                raise _LimitExceeded("output_characters")
            meaningful, sufficient = _quality(text)
            pages.append(PdfPage(number, text, meaningful, sufficient, has_image, has_graphics))
        if monitor.seen:
            return PdfExtraction(PdfOutcome.CORRUPT, reason="parser_warning")
        if not any(page.text for page in pages) and any(page.has_image for page in pages):
            outcome, reason = PdfOutcome.IMAGE_ONLY, "no_native_text"
        elif not any(page.sufficient for page in pages):
            outcome, reason = PdfOutcome.INSUFFICIENT_TEXT, "native_text_threshold"
        elif any(
            not page.sufficient and (page.text or page.has_image or page.has_graphics)
            for page in pages
        ):
            outcome, reason = PdfOutcome.INSUFFICIENT_TEXT, "partial_native_text"
        else:
            outcome, reason = PdfOutcome.OK, None
        return PdfExtraction(outcome, tuple(pages), count, reason)
    except _LimitExceeded as exc:
        return PdfExtraction(PdfOutcome.RESOURCE_LIMIT, reason=str(exc))
    except _EncryptedInput:
        return PdfExtraction(PdfOutcome.ENCRYPTED, reason="password_protected")
    except LimitReachedError:
        return PdfExtraction(PdfOutcome.RESOURCE_LIMIT, reason="native_parser_limit")
    except MemoryError:
        return PdfExtraction(PdfOutcome.RESOURCE_LIMIT, reason="memory_bytes")
    except (DependencyError, NotImplementedError):
        return PdfExtraction(PdfOutcome.UNSUPPORTED, reason="native_feature")
    except (PyPdfError, ValueError, KeyError, TypeError, IndexError, RecursionError):
        return PdfExtraction(PdfOutcome.CORRUPT, reason="invalid_pdf")
    finally:
        overwrite_configuration(previous_configuration)
        parser_logger.removeHandler(monitor)
        parser_logger.setLevel(previous_level)
        parser_logger.propagate = previous_propagation
        monitor.close()


def _worker_main() -> None:
    import resource

    limits = PdfLimits(**json.loads(sys.argv[1]))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        resource.setrlimit(
            resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 1)
        )
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (OSError, ValueError):
        result = PdfExtraction(PdfOutcome.ISOLATION_UNAVAILABLE, reason="os_limits")
    else:
        try:
            # Functions deployments vendor dependencies here; isolated mode ignores
            # worker-added PYTHONPATH. Only this fixed deployment-owned path is added.
            packages = Path(__file__).resolve().parents[1] / ".python_packages/lib/site-packages"
            if packages.is_dir():
                sys.path.insert(0, str(packages))
            data = sys.stdin.buffer.read(limits.max_input_bytes + 1)
            if len(data) > limits.max_input_bytes:
                result = PdfExtraction(PdfOutcome.RESOURCE_LIMIT, reason="input_bytes")
            else:
                result = _parse_pdf(data, limits)
        except ModuleNotFoundError:
            result = PdfExtraction(PdfOutcome.PARSER_UNAVAILABLE, reason="dependency")
        except MemoryError:
            # Leave a fixed exit code if even serializing a small failure is impossible.
            sys.exit(20)
    try:
        sys.stdout.buffer.write(json.dumps(asdict(result), ensure_ascii=True).encode("ascii"))
    except MemoryError:
        sys.exit(20)


if __name__ == "__main__":
    _worker_main()
