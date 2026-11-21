from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.deck import DeckError, DeckIdentity, validate_deck_name

if TYPE_CHECKING:
    from anki.collection import Collection, OpChangesWithId


def list_decks(collection: Collection) -> tuple[DeckIdentity, ...]:
    if collection is None:
        raise DeckError("collection")
    return tuple(
        DeckIdentity(int(deck.id), deck.name)
        for deck in collection.decks.all_names_and_ids(
            skip_empty_default=False, include_filtered=False
        )
    )


def revalidate_deck(
    collection: Collection, target: DeckIdentity | None
) -> DeckIdentity:
    """Resolve only the captured ID, never a reused name or Anki's default fallback."""
    if target is None:
        raise DeckError("unselected")
    for deck in list_decks(collection):
        if deck.deck_id == target.deck_id:
            return deck
    raise DeckError("missing")


def create_deck(collection: Collection, name: str) -> OpChangesWithId:
    name = validate_deck_name(name)
    if collection is None:
        raise DeckError("collection")
    if collection.decks.id_for_name(name) is not None:
        raise DeckError("exists")
    return collection.decks.add_normal_deck_with_name(name)
