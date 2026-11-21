"""Anki loads this package; no network or credential access occurs at import."""

from .ui.bootstrap import install

install(__name__)
