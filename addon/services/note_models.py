from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models.deck import DeckIdentity
from ..models.note_payload import (
    BasicFields, ClozeFields, GeneratedNote, ModelFamily, NoteMappingError,
    parse_generated_note,
)
from .decks import revalidate_deck
from .markup import escape_metadata, sanitize_html

if TYPE_CHECKING:
    from anki.collection import Collection, OpChangesWithId
    from anki.models import NotetypeDict
    from anki.notes import Note


_METADATA_FIELDS = ("Source", "Import ID", "Payload Version", "Provenance")
_CSS = ".card { font-family: Arial; font-size: 20px; text-align: left; }\n.cloze { font-weight: bold; color: blue; }"
_SOURCE = "<hr><div>{{Source}}</div>"
_BASIC_TEMPLATES = (
    ("Forward", "{{Front}}", "{{FrontSide}}<hr id=answer>{{Back}}" + _SOURCE),
)
_REVERSED_TEMPLATES = _BASIC_TEMPLATES + (
    ("Reverse", "{{Back}}", "{{FrontSide}}<hr id=answer>{{Front}}" + _SOURCE),
)
_CLOZE_TEMPLATES = (
    ("Cloze", "{{cloze:Text}}", "{{cloze:Text}}<br>{{Back Extra}}" + _SOURCE),
)


def model_name(family: ModelFamily) -> str:
    if family not in ("basic", "reversed", "cloze"):
        raise NoteMappingError("payload", "model_family")
    return f"Anki AI Deck Generator::{family}::v1"


def _fields(family: ModelFamily) -> tuple[str, ...]:
    return (("Text", "Back Extra") if family == "cloze" else ("Front", "Back")) + _METADATA_FIELDS


def _templates(family: ModelFamily) -> tuple[tuple[str, str, str], ...]:
    if family == "cloze":
        return _CLOZE_TEMPLATES
    return _REVERSED_TEMPLATES if family == "reversed" else _BASIC_TEMPLATES


def _validate_model(model: NotetypeDict, family: ModelFamily) -> None:
    fields = model.get("flds")
    if (
        not isinstance(fields, list)
        or any(not isinstance(field, dict) for field in fields)
        or tuple(field.get("name") for field in fields) != _fields(family)
        or any(field.get("ord") != index for index, field in enumerate(fields))
    ):
        raise NoteMappingError("model_fields")
    templates = model.get("tmpls")
    if (
        model.get("name") != model_name(family)
        or type(model.get("type")) is not int
        or model["type"] != (1 if family == "cloze" else 0)
        or model.get("sortf") != 0
        or model.get("css") != _CSS
        or not isinstance(templates, list)
        or any(not isinstance(template, dict) for template in templates)
        or tuple((template.get("name"), template.get("qfmt"), template.get("afmt"))
                 for template in templates) != _templates(family)
        or any(template.get("ord") != index for index, template in enumerate(templates))
        or any(template.get("did") not in (None, 0)
               or template.get("bqfmt") not in (None, "")
               or template.get("bafmt") not in (None, "")
               for template in templates)
    ):
        raise NoteMappingError("model_collision")


def _resolve_model(
    collection: Collection, family: ModelFamily, create: bool,
) -> tuple[NotetypeDict, OpChangesWithId | None]:
    manager = collection.models
    name = model_name(family)
    model = manager.by_name(name)
    if model is not None:
        _validate_model(model, family)
        return model, None
    if not create:
        raise NoteMappingError("model_missing")
    model = manager.new(name)
    model["type"] = 1 if family == "cloze" else 0
    model["sortf"] = 0
    model["css"] = _CSS
    for field_name in _fields(family):
        manager.add_field(model, manager.new_field(field_name))
    for template_name, question, answer in _templates(family):
        template = manager.new_template(template_name)
        template["qfmt"], template["afmt"] = question, answer
        manager.add_template(model, template)
    changes = manager.add_dict(model)
    saved = manager.get(changes.id)
    if saved is None:
        raise NoteMappingError("model_missing")
    _validate_model(saved, family)
    return saved, changes


def _mapped_fields(payload: GeneratedNote) -> dict[str, str]:
    if isinstance(payload.fields, BasicFields):
        values = {"Front": payload.fields.front, "Back": payload.fields.back}
    elif isinstance(payload.fields, ClozeFields):
        values = {"Text": payload.fields.text, "Back Extra": payload.fields.back_extra}
    else:
        raise NoteMappingError("payload", "fields")
    sanitized = {}
    for name, value in values.items():
        try:
            sanitized[name] = sanitize_html(
                value, allow_empty=name == "Back Extra", cloze=name == "Text",
            )
        except NoteMappingError as error:
            raise NoteMappingError(error.code, f"fields.{name}") from None
    source = payload.source
    display = [source.name]
    for label, value in (("page", source.page), ("slide", source.slide), ("section", source.section)):
        if value is not None:
            display.append(f"{label}: {value}")
    provenance = {
        "source": {
            "document_id": source.document_id, "sha256": source.sha256, "name": source.name,
            "location": {"page": source.page, "slide": source.slide, "section": source.section},
        },
        "model_family": payload.model_family,
        "prompt_version": payload.prompt_version, "model_version": payload.model_version,
    }
    sanitized.update({
        "Source": escape_metadata("; ".join(display)),
        "Import ID": payload.import_id,
        "Payload Version": str(payload.schema_version),
        "Provenance": escape_metadata(json.dumps(provenance, ensure_ascii=True, sort_keys=True,
                                                separators=(",", ":"))),
    })
    return sanitized


@dataclass(frozen=True, repr=False)
class MappedNote:
    note: Note
    deck: DeckIdentity
    model_changes: OpChangesWithId | None


def map_generated_note(
    collection: Collection, value: object, target: DeckIdentity,
    *, create_model: bool = False,
) -> MappedNote:
    """Run in the originating serialized collection operation; never insert."""
    if type(create_model) is not bool:
        raise NoteMappingError("payload", "create_model")
    payload = parse_generated_note(value)
    values = _mapped_fields(payload)
    if collection is None:
        raise NoteMappingError("collection")
    deck = revalidate_deck(collection, target)
    model, changes = _resolve_model(collection, payload.model_family, create_model)
    note = collection.new_note(model)
    for field_name, content in values.items():
        try:
            note[field_name] = content
        except KeyError:
            raise NoteMappingError("model_fields", field_name) from None
    return MappedNote(note, deck, changes)
