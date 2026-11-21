from dataclasses import asdict, dataclass
from enum import StrEnum
import logging
import re
import unicodedata


EXTRACTION_VERSION = "text-native-1"


class TextFormat(StrEnum):
    TXT = "txt"
    MARKDOWN = "markdown"


class TextOutcome(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    INVALID_ENCODING = "invalid_encoding"
    RESOURCE_LIMIT = "resource_limit"


@dataclass(frozen=True)
class TextLimits:
    max_input_bytes: int = 4 * 1024 * 1024
    max_lines: int = 100_000
    max_sections: int = 10_000
    max_output_characters: int = 1_000_000

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("Text limits must be positive integers.")


@dataclass(frozen=True)
class TextSection:
    headings: tuple[str, ...]
    line_start: int
    line_end: int
    text: str


@dataclass(frozen=True)
class TextExtraction:
    outcome: TextOutcome
    source_format: TextFormat
    sections: tuple[TextSection, ...] = ()
    reason: str | None = None
    version: str = EXTRACTION_VERSION


_ATX_HEADING = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$")
_SETEXT_HEADING = re.compile(r" {0,3}(=+|-+)[ \t]*$")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)$")
_CLOSING_ATX = re.compile(r"[ \t]+#+[ \t]*$")


def _failure(
    source_format: TextFormat,
    outcome: TextOutcome,
    reason: str,
) -> TextExtraction:
    logging.warning("text_extraction: %s (%s)", outcome.value, reason)
    return TextExtraction(outcome, source_format, reason=reason)


def extract_txt(data: bytes, limits: TextLimits = TextLimits()) -> TextExtraction:
    return _extract(data, TextFormat.TXT, limits)


def extract_markdown(
    data: bytes,
    limits: TextLimits = TextLimits(),
) -> TextExtraction:
    return _extract(data, TextFormat.MARKDOWN, limits)


def _extract(
    data: bytes,
    source_format: TextFormat,
    limits: TextLimits,
) -> TextExtraction:
    if not isinstance(data, bytes):
        raise TypeError("Text input must be bytes.")
    if len(data) > limits.max_input_bytes:
        return _failure(source_format, TextOutcome.RESOURCE_LIMIT, "input_bytes")

    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _failure(source_format, TextOutcome.INVALID_ENCODING, "invalid_utf8")

    normalized = unicodedata.normalize("NFC", decoded.replace("\r\n", "\n").replace("\r", "\n"))
    line_count = normalized.count("\n") + 1
    if line_count > limits.max_lines:
        return _failure(source_format, TextOutcome.RESOURCE_LIMIT, "line_count")
    if not normalized.strip():
        return _failure(source_format, TextOutcome.EMPTY, "empty_document")

    lines = normalized.split("\n")
    if source_format == TextFormat.MARKDOWN:
        headings, setext_underlines = _find_headings(lines)
    else:
        headings, setext_underlines = {}, set()

    sections: list[TextSection] = []
    current_headings: tuple[str, ...] = ()
    current_heading_line: int | None = None
    current_lines: list[tuple[int, str]] = []
    heading_stack: list[tuple[int, str]] = []
    output_characters = 0

    def flush() -> bool:
        nonlocal output_characters
        nonempty = [
            index for index, (_, line) in enumerate(current_lines)
            if line.strip()
        ]
        if current_heading_line is None and not nonempty:
            return True

        if nonempty:
            first, last = nonempty[0], nonempty[-1]
            body_lines = current_lines[first:last + 1]
            body = "\n".join(line for _, line in body_lines)
            line_start = (
                current_heading_line
                if current_heading_line is not None
                else body_lines[0][0]
            )
            line_end = body_lines[-1][0]
        else:
            assert current_heading_line is not None
            body = ""
            line_start = line_end = current_heading_line

        section = TextSection(current_headings, line_start, line_end, body)
        if len(sections) >= limits.max_sections:
            return False
        section_characters = len(body) + sum(
            len(heading) for heading in current_headings
        )
        if output_characters + section_characters > limits.max_output_characters:
            return False
        output_characters += section_characters
        sections.append(section)
        return True

    for index, line in enumerate(lines):
        line_number = index + 1
        heading = headings.get(index)
        if heading is not None:
            if not flush():
                reason = (
                    "section_count"
                    if len(sections) >= limits.max_sections
                    else "output_characters"
                )
                return _failure(source_format, TextOutcome.RESOURCE_LIMIT, reason)
            level, title = heading
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current_headings = tuple(item[1] for item in heading_stack)
            current_heading_line = line_number
            current_lines = []
        elif index not in setext_underlines:
            current_lines.append((line_number, line))

    if not flush():
        reason = (
            "section_count"
            if len(sections) >= limits.max_sections
            else "output_characters"
        )
        return _failure(source_format, TextOutcome.RESOURCE_LIMIT, reason)
    return TextExtraction(TextOutcome.OK, source_format, tuple(sections))


def _find_headings(lines: list[str]) -> tuple[dict[int, tuple[int, str]], set[int]]:
    headings: dict[int, tuple[int, str]] = {}
    setext_underlines: set[int] = set()
    fence_boundaries: set[int] = set()
    fence_character: str | None = None
    fence_length = 0

    for index, line in enumerate(lines):
        if fence_character is not None:
            closing = re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
                line,
            )
            if closing:
                fence_character = None
                fence_length = 0
                fence_boundaries.add(index)
            continue

        fence = _FENCE.fullmatch(line)
        if fence and not (fence.group(1)[0] == "`" and "`" in fence.group(2)):
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            fence_boundaries.add(index)
            continue

        atx = _ATX_HEADING.fullmatch(line)
        if atx:
            title = atx.group(2) or ""
            title = _CLOSING_ATX.sub("", title).strip()
            if not title.strip("# \t"):
                title = ""
            headings[index] = (len(atx.group(1)), title)
            continue

        setext = _SETEXT_HEADING.fullmatch(line)
        previous = index - 1
        if (
            setext
            and previous >= 0
            and lines[previous].strip()
            and previous not in headings
            and previous not in setext_underlines
            and previous not in fence_boundaries
        ):
            title = lines[previous].strip()
            headings[previous] = (1 if setext.group(1)[0] == "=" else 2, title)
            setext_underlines.add(index)

    return headings, setext_underlines
