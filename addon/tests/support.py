import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Unit tests load core modules without invoking Anki's entry point.
package = types.ModuleType("addon")
package.__path__ = [str(ROOT)]
sys.modules.setdefault("addon", package)


def load_build():
    spec = importlib.util.spec_from_file_location("addon_build", ROOT / "tools" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyntheticDecks:
    def __init__(self):
        self.names = {1: "Default", 101: "Synthetic::Biology", 202: "Synthetic::History"}
        self.filtered = {303: "Synthetic filtered deck"}
        self.calls = []

    def all_names_and_ids(self, *, skip_empty_default, include_filtered):
        self.calls.append(("list", skip_empty_default, include_filtered))
        names = {**self.names, **self.filtered} if include_filtered else self.names
        return [types.SimpleNamespace(id=deck_id, name=name)
                for deck_id, name in sorted(names.items(), key=lambda item: item[1])]

    def id_for_name(self, name):
        self.calls.append(("lookup", name))
        for deck_id, existing in {**self.names, **self.filtered}.items():
            if existing.casefold() == name.casefold():
                return deck_id
        return None

    def add_normal_deck_with_name(self, name):
        self.calls.append(("create", name))
        deck_id = max({**self.names, **self.filtered}) + 1
        self.names[deck_id] = name
        return types.SimpleNamespace(id=deck_id, changes=types.SimpleNamespace(deck=True))
