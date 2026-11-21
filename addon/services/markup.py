from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

from ..models.note_payload import NoteMappingError


_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "s", "sub", "sup", "p", "div", "span",
    "br", "ul", "ol", "li", "pre", "code", "blockquote", "table", "thead",
    "tbody", "tr", "th", "td",
})


class _MarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.text: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _TAGS or len(self.stack) >= 32:
            raise NoteMappingError("markup")
        # No attributes survive, including URLs, style, events and hidden state.
        self.parts.append(f"<{tag}>")
        if tag != "br":
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            raise NoteMappingError("markup")
        self.stack.pop()
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data, quote=True))
        self.text.append(data)

    def handle_decl(self, decl: str) -> None:
        raise NoteMappingError("markup")

    def handle_comment(self, data: str) -> None:
        raise NoteMappingError("markup")

    def handle_pi(self, data: str) -> None:
        raise NoteMappingError("markup")

    def unknown_decl(self, data: str) -> None:
        raise NoteMappingError("markup")


def _parse(value: str) -> _MarkupParser:
    if (
        not isinstance(value, str)
        or len(value) > 32768
        or any(
            (ord(char) < 32 and char not in "\t\n\r")
            or 127 <= ord(char) <= 159
            or 0xD800 <= ord(char) <= 0xDFFF
            for char in value
        )
    ):
        raise NoteMappingError("markup")
    parser = _MarkupParser()
    parser.feed(value)
    parser.close()
    if parser.stack:
        raise NoteMappingError("markup")
    return parser


def sanitize_html(value: str, *, allow_empty: bool = False, cloze: bool = False) -> str:
    parser = _parse(value)
    html = "".join(parser.parts)
    text = "".join(parser.text)
    if re.search(r"\[(?:/?latex|/?\$\$?|sound:)", text, re.IGNORECASE):
        raise NoteMappingError("markup")
    if not text.strip() and not allow_empty:
        raise NoteMappingError("field")
    if cloze:
        _validate_cloze(html)
    elif "{{" in html or "}}" in html:
        raise NoteMappingError("cloze")
    return html


def _validate_cloze(html: str) -> None:
    pattern = r"\{\{c([1-9][0-9]?)::([^{}]+)\}\}"
    matches = list(re.finditer(pattern, html))
    remaining = re.sub(pattern, "", html)
    if not matches or "{{" in remaining or "}}" in remaining:
        raise NoteMappingError("cloze")
    for match in matches:
        parts = match[2].split("::")
        if len(parts) > 2:
            raise NoteMappingError("cloze")
        for part in parts:
            try:
                parsed = _parse(part)
            except NoteMappingError:
                raise NoteMappingError("cloze") from None
            if not "".join(parsed.text).strip():
                raise NoteMappingError("cloze")


def escape_metadata(value: str) -> str:
    """Keep Anki's non-HTML media/LaTeX/cloze syntax literal as well."""
    escaped = escape(value, quote=True)
    for char in "[]{}":
        escaped = escaped.replace(char, f"&#{ord(char)};")
    return escaped
