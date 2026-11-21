from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


class NoteMappingError(Exception):
    MESSAGES = {
        "version": "Unsupported note payload version. Request a compatible result.",
        "payload": "The generated note payload has missing, unknown or invalid properties.",
        "field": "A generated note field is missing, empty or invalid. Review the result.",
        "markup": "Generated markup is unsupported or malformed. Review the result.",
        "cloze": "Cloze text requires valid, nonempty c1-c99 deletions without nesting.",
        "model_missing": "The required versioned note model is absent. Explicit model creation is required.",
        "model_collision": "The versioned model name or templates conflict with an existing model. No model was overwritten.",
        "model_fields": "The versioned note model has incompatible fields. No model was changed.",
        "collection": "The collection is unavailable. Open the originating profile and retry.",
    }

    def __init__(self, code: str, field: str | None = None):
        self.code = code
        self.field = field
        super().__init__(self.MESSAGES[code])


ModelFamily = Literal["basic", "reversed", "cloze"]


@dataclass(frozen=True, repr=False)
class BasicFields:
    front: str
    back: str


@dataclass(frozen=True, repr=False)
class ClozeFields:
    text: str
    back_extra: str


@dataclass(frozen=True, repr=False)
class Source:
    document_id: str
    sha256: str
    name: str
    page: int | None
    slide: int | None
    section: str | None


@dataclass(frozen=True, repr=False)
class GeneratedNote:
    schema_version: Literal[1]
    model_family: ModelFamily
    import_id: str
    fields: BasicFields | ClozeFields
    source: Source
    prompt_version: str
    model_version: str


def _object(value: object, keys: set[str], path: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise NoteMappingError("payload", path)
    return value


def _text(value: object, limit: int, path: str, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (not empty and not value.strip())
        or any(
            (ord(char) < 32 and char not in "\t\n\r")
            or 127 <= ord(char) <= 159
            or 0xD800 <= ord(char) <= 0xDFFF
            for char in value
        )
    ):
        raise NoteMappingError("field", path)
    return value


def _label(value: object, path: str) -> str:
    text = _text(value, 255, path)
    if any(ord(char) < 32 for char in text):
        raise NoteMappingError("field", path)
    return text


def _uuid(value: object, path: str) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise NoteMappingError("payload", path)
    try:
        parsed = UUID(value)
    except ValueError:
        raise NoteMappingError("payload", path) from None
    if str(parsed) != value:
        raise NoteMappingError("payload", path)
    return value


def _coordinate(value: object, path: str) -> int | None:
    if value is not None and (type(value) is not int or not 1 <= value <= 2**31 - 1):
        raise NoteMappingError("payload", path)
    return value


def parse_generated_note(value: object) -> GeneratedNote:
    """Parse one JSON note, rejecting unknown keys and all implicit coercion."""
    raw = _object(value, {
        "schema_version", "model_family", "import_id", "fields", "source",
        "prompt_version", "model_version",
    }, "payload")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise NoteMappingError("version", "schema_version")
    family: ModelFamily
    if raw["model_family"] == "basic":
        family = "basic"
    elif raw["model_family"] == "reversed":
        family = "reversed"
    elif raw["model_family"] == "cloze":
        family = "cloze"
    else:
        raise NoteMappingError("payload", "model_family")
    fields: BasicFields | ClozeFields
    if family == "cloze":
        field_values = _object(raw["fields"], {"Text", "Back Extra"}, "fields")
        fields = ClozeFields(
            _text(field_values["Text"], 32768, "fields.Text"),
            _text(field_values["Back Extra"], 32768, "fields.Back Extra", empty=True),
        )
    else:
        field_values = _object(raw["fields"], {"Front", "Back"}, "fields")
        fields = BasicFields(
            _text(field_values["Front"], 32768, "fields.Front"),
            _text(field_values["Back"], 32768, "fields.Back"),
        )
    source = _object(raw["source"], {
        "document_id", "sha256", "name", "location",
    }, "source")
    location = _object(source["location"], {"page", "slide", "section"}, "source.location")
    sha256 = source["sha256"]
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise NoteMappingError("payload", "source.sha256")
    versions = []
    for key in ("prompt_version", "model_version"):
        version = raw[key]
        if not isinstance(version, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version) is None:
            raise NoteMappingError("payload", key)
        versions.append(version)
    return GeneratedNote(
        1, family, _uuid(raw["import_id"], "import_id"), fields,
        Source(
            _uuid(source["document_id"], "source.document_id"), sha256,
            _label(source["name"], "source.name"),
            _coordinate(location["page"], "source.location.page"),
            _coordinate(location["slide"], "source.location.slide"),
            None if location["section"] is None else _label(location["section"], "source.location.section"),
        ),
        versions[0], versions[1],
    )
