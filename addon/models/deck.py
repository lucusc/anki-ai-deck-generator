from dataclasses import dataclass, field
from unicodedata import normalize


class DeckError(Exception):
    MESSAGES = {
        "name": "Enter a deck name with nonempty ::-separated parts, no control characters, quotes, edge colons or edge whitespace.",
        "exists": "A deck with that name already exists. Refresh the list and select it instead.",
        "missing": "The selected deck was deleted or is now filtered. Select another normal deck; no fallback deck was chosen.",
        "unselected": "Select a destination deck before continuing.",
        "closed": "Deck operation cancelled because the workflow or profile closed.",
        "collection": "The collection is unavailable. Open a profile and retry.",
    }

    def __init__(self, code: str):
        self.code = code
        super().__init__(self.MESSAGES[code])


@dataclass(frozen=True, repr=False)
class DeckIdentity:
    deck_id: int
    name: str

    def __repr__(self) -> str:
        return "DeckIdentity(<local collection target>)"


@dataclass
class DeckSelection:
    target: DeckIdentity | None = field(default=None, repr=False)


def validate_deck_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or any(ord(char) < 32 or 127 <= ord(char) <= 159 or char == '"' for char in name)
        or any(not part or part != part.strip().strip(":") for part in name.split("::"))
    ):
        raise DeckError("name")
    return normalize("NFC", name)
