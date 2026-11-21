from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models.deck import DeckIdentity
from ..models.note_payload import BasicFields, NoteMappingError, parse_generated_note
from .basic_notes import (
    BasicImportTarget, _basic_snapshot, _validate_target, capture_basic_target,
)
from .decks import revalidate_deck
from .note_models import map_generated_note, model_name

if TYPE_CHECKING:
    from anki.cards import Card
    from anki.collection import Collection, OpChanges, OpChangesWithCount, OpChangesWithId
    from anki.notes import Note


class ReversedImportError(Exception):
    MESSAGES = {
        "approval": "Explicit approval is required before importing a note.",
        "family": "Only Basic and reversed notes can be imported by this operation.",
        "lifetime": "The originating collection is unavailable. Select the destination again.",
        "budget": "A nonnegative integer remaining card budget is required.",
        "limit": "This reversed note requires two additional cards. Increase the card budget or exclude it.",
        "identity": "The import identity conflicts with saved content, model or destination. Review before retrying.",
        "cards": "The saved note does not have the expected two destination cards. Reconcile the import before retrying.",
        "render": "Both directions require visible question text. Review the note before importing.",
        "saved_state": "The saved import differs from the approved note. Reconcile collection state before retrying.",
    }

    def __init__(self, code: str):
        self.code = code
        super().__init__(self.MESSAGES[code])


@dataclass(frozen=True, repr=False)
class ReversedImportResult:
    note_id: int
    deck: DeckIdentity
    card_ids: tuple[int, ...]
    reused: bool
    note_changes: OpChangesWithCount | None
    model_changes: OpChangesWithId | None

    @property
    def note_count(self) -> int:
        return 1

    @property
    def card_count(self) -> int:
        return len(self.card_ids)

    @property
    def added_note_count(self) -> int:
        return 0 if self.reused else self.note_count

    @property
    def added_card_count(self) -> int:
        return 0 if self.reused else self.card_count

    @property
    def changes(self) -> OpChanges:
        if self.note_changes is not None:
            return self.note_changes.changes
        from anki.collection import OpChanges

        return OpChanges()


def capture_reversed_target(
    collection: Collection, target: DeckIdentity | None,
) -> BasicImportTarget:
    """Capture the same collection-bound logical numeric target as Basic."""
    return capture_basic_target(collection, target)


def _prior_import(collection: Collection, import_id: str) -> Note | None:
    # Canonical UUIDs contain no Anki search operators or wildcard characters.
    matches = []
    for note_id in collection.find_notes(f'"Import ID:{import_id}"'):
        note = collection.get_note(note_id)
        if dict(note.items()).get("Import ID") == import_id:
            matches.append(note)
    if len(matches) > 1:
        raise ReversedImportError("identity")
    if not matches:
        return None
    model = matches[0].note_type()
    if model is None or model["name"] != model_name("reversed"):
        raise ReversedImportError("identity")
    return matches[0]


def _validate_rendering(cards: list[Card]) -> None:
    from anki.utils import strip_html

    for card in cards:
        output = card.render_output()
        question = strip_html(output.question_text)
        if not any(not char.isspace() and unicodedata.category(char)[0] != "C" for char in question):
            raise ReversedImportError("render")
        # Render both faces now so an answer-side failure is not reported as success.
        card.answer()


def _saved_cards(note: Note, deck: DeckIdentity) -> list[Card]:
    cards = sorted(note.cards(), key=lambda card: card.ord)
    if (
        len(cards) != 2
        or tuple(card.ord for card in cards) != (0, 1)
        or any(card.nid != note.id or card.did != deck.deck_id for card in cards)
    ):
        raise ReversedImportError("cards")
    _validate_rendering(cards)
    return cards


def import_approved_reversed(
    collection: Collection,
    value: object,
    target: BasicImportTarget,
    *,
    approved: bool,
    remaining_cards: int,
    create_model: bool = False,
) -> ReversedImportResult:
    """Import or verify one approved logical note in a serialized collection operation."""
    if approved is not True:
        raise ReversedImportError("approval")
    if type(remaining_cards) is not int or remaining_cards < 0:
        raise ReversedImportError("budget")
    if type(create_model) is not bool:
        raise NoteMappingError("payload", "create_model")
    payload = parse_generated_note(value)
    if payload.model_family != "reversed" or not isinstance(payload.fields, BasicFields):
        raise ReversedImportError("family")
    if not isinstance(target, BasicImportTarget) or collection is None or target._collection is not collection:
        raise ReversedImportError("lifetime")
    _validate_target(target.deck)
    snapshot = _basic_snapshot(payload)
    deck = revalidate_deck(collection, target.deck)
    prior = _prior_import(collection, payload.import_id)
    if prior is None and remaining_cards < 2:
        raise ReversedImportError("limit")

    mapped = map_generated_note(
        collection, snapshot, deck, create_model=create_model if prior is None else False,
    )
    expected = dict(mapped.note.items())
    expected_model = mapped.note.mid
    if prior is not None:
        if prior.mid != expected_model or dict(prior.items()) != expected:
            raise ReversedImportError("identity")
        cards = _saved_cards(prior, mapped.deck)
        return ReversedImportResult(
            prior.id, mapped.deck, tuple(card.id for card in cards), True, None, None,
        )

    # The strict v1 model plus nonempty fields generates two cards on both supported cores.
    # Render before insertion, then verify actual saved cards rather than counting templates.
    _validate_rendering([mapped.note.ephemeral_card(ordinal) for ordinal in (0, 1)])
    note_changes = collection.add_note(mapped.note, mapped.deck.deck_id)
    saved = collection.get_note(mapped.note.id)
    if saved.mid != expected_model or dict(saved.items()) != expected:
        raise ReversedImportError("saved_state")
    cards = _saved_cards(saved, mapped.deck)
    if mapped.model_changes is not None:
        note_changes.changes.MergeFrom(mapped.model_changes.changes)
    return ReversedImportResult(
        saved.id, mapped.deck, tuple(card.id for card in cards), False,
        note_changes, mapped.model_changes,
    )
