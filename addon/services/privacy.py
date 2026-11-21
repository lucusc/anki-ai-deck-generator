import logging

from ..models.auth import AddonError

LOGGER = logging.getLogger("anki_ai_deck_generator")


def event(code: str) -> None:
    if code not in AddonError.MESSAGES and code not in {"loaded", "signed_in", "signed_out_ok"}:
        raise ValueError("Unknown operational event")
    # No exception strings, URLs, tokens, profile names or response bodies.
    LOGGER.info("anki_ai_deck_generator event=%s", code)
