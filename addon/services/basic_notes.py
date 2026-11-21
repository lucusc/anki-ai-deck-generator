from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models.deck import DeckError, DeckIdentity
from ..models.note_payload import BasicFields, GeneratedNote, NoteMappingError, parse_generated_note
from .decks import revalidate_deck
from .note_models import map_generated_note

if TYPE_CHECKING:
    from anki.collection import Collection, OpChanges, OpChangesWithCount, OpChangesWithId


class BasicImportError(Exception):
    MESSAGES = {
        "approval": "Explicit approval is required before importing a note.",
        "family": "Only Basic notes can be imported by this operation.",
        "lifetime": "The originating collection is unavailable. Select the destination again.",
        "target": "The captured destination is invalid. Select a normal deck again.",
    }

    def __init__(self, code: str):
        self.code = code
        super().__init__(self.MESSAGES[code])


@dataclass(frozen=True, repr=False)
class BasicImportTarget:
    _collection: Collection
    deck: DeckIdentity


@dataclass(frozen=True, repr=False)
class BasicImportResult:
    note_id: int
    deck: DeckIdentity
    note_changes: OpChangesWithCount
    model_changes: OpChangesWithId | None

    @property
    def changes(self) -> OpChanges:
        return self.note_changes.changes


def _validate_target(target: DeckIdentity | None) -> None:
    if target is None:
        raise DeckError("unselected")
    if (
        not isinstance(target, DeckIdentity)
        or type(target.deck_id) is not int
        or target.deck_id <= 0
        or not isinstance(target.name, str)
    ):
        raise BasicImportError("target")


def capture_basic_target(collection: Collection, target: DeckIdentity | None) -> BasicImportTarget:
    """Capture a destination in its originating serialized collection operation."""
    _validate_target(target)
    return BasicImportTarget(collection, revalidate_deck(collection, target))


def _basic_snapshot(payload: GeneratedNote) -> dict[str, object]:
    if not isinstance(payload.fields, BasicFields):
        raise NoteMappingError("payload", "fields")
    source = payload.source
    return {
        "schema_version": payload.schema_version,
        "model_family": payload.model_family,
        "import_id": payload.import_id,
        "fields": {"Front": payload.fields.front, "Back": payload.fields.back},
        "source": {
            "document_id": source.document_id,
            "sha256": source.sha256,
            "name": source.name,
            "location": {"page": source.page, "slide": source.slide, "section": source.section},
        },
        "prompt_version": payload.prompt_version,
        "model_version": payload.model_version,
    }


def import_approved_basic(
    collection: Collection,
    value: object,
    target: BasicImportTarget,
    *,
    approved: bool,
    create_model: bool = False,
) -> BasicImportResult:
    """Insert one explicitly approved Basic note inside its collection operation."""
    if approved is not True:
        raise BasicImportError("approval")
    if type(create_model) is not bool:
        raise NoteMappingError("payload", "create_model")
    payload = parse_generated_note(value)
    if payload.model_family != "basic" or not isinstance(payload.fields, BasicFields):
        raise BasicImportError("family")
    if not isinstance(target, BasicImportTarget) or collection is None or target._collection is not collection:
        raise BasicImportError("lifetime")
    _validate_target(target.deck)

    snapshot = _basic_snapshot(payload)
    mapped = map_generated_note(collection, snapshot, target.deck, create_model=create_model)
    note_changes = collection.add_note(mapped.note, mapped.deck.deck_id)
    if mapped.model_changes is not None:
        note_changes.changes.MergeFrom(mapped.model_changes.changes)
    return BasicImportResult(mapped.note.id, mapped.deck, note_changes, mapped.model_changes)
