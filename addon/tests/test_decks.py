import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import support
from addon.models.deck import DeckError, DeckIdentity, DeckSelection, validate_deck_name
from addon.services.decks import create_deck, list_decks, revalidate_deck


class DeckTests(unittest.TestCase):
    def setUp(self):
        self.collection = types.SimpleNamespace(decks=support.SyntheticDecks())

    def test_existing_selection_is_id_based_and_read_only(self):
        decks = list_decks(self.collection)
        self.assertEqual({deck.deck_id for deck in decks}, {1, 101, 202})
        target = next(deck for deck in decks if deck.deck_id == 101)
        selection = DeckSelection(target)
        self.assertEqual(revalidate_deck(self.collection, selection.target), target)
        self.assertTrue(all(call == ("list", False, False)
                            for call in self.collection.decks.calls))
        self.assertNotIn("Biology", repr(target))

    def test_rename_retains_id_and_deleted_name_reuse_never_redirects(self):
        target = DeckIdentity(101, "Synthetic::Biology")
        self.collection.decks.names[101] = "Synthetic::Renamed"
        renamed = revalidate_deck(self.collection, target)
        self.assertEqual(renamed.deck_id, 101)
        self.assertEqual(renamed.name, "Synthetic::Renamed")
        del self.collection.decks.names[101]
        self.collection.decks.names[404] = target.name
        with self.assertRaises(DeckError) as error:
            revalidate_deck(self.collection, target)
        self.assertEqual(error.exception.code, "missing")

    def test_no_selection_filtered_target_or_closed_collection_fail_explicitly(self):
        for collection, target, code in (
            (self.collection, None, "unselected"),
            (self.collection, DeckIdentity(303, "Synthetic filtered deck"), "missing"),
            (None, DeckIdentity(101, "Synthetic::Biology"), "collection"),
        ):
            with self.subTest(code=code), self.assertRaises(DeckError) as error:
                revalidate_deck(collection, target)
            self.assertEqual(error.exception.code, code)

    def test_new_deck_creation_returns_supported_change_result_and_exact_id(self):
        result = create_deck(self.collection, "Synthetic::Chemistry")
        self.assertTrue(result.changes.deck)
        self.assertEqual(self.collection.decks.names[result.id], "Synthetic::Chemistry")
        self.assertEqual(self.collection.decks.calls,
                         [("lookup", "Synthetic::Chemistry"), ("create", "Synthetic::Chemistry")])
        self.assertEqual(revalidate_deck(
            self.collection, DeckIdentity(result.id, "Synthetic::Chemistry")
        ).deck_id, result.id)
        self.assertEqual(create_deck(self.collection, "Synthetic::Cafe\u0301").id, 305)
        self.assertEqual(self.collection.decks.names[305], "Synthetic::Caf\u00e9")

    def test_invalid_names_do_not_touch_collection(self):
        for name in ("", " ", " Leading", "Trailing ", "::Child", "Parent::",
                     "Parent::::Child", "Parent:: Child", "Private\nName",
                     "Private\x1fName", 'Quoted"Name', "Control\x7fName", None,
                     ":", ":Deck", "Deck:", "Parent:::Child"):
            with self.subTest(name=name), self.assertRaises(DeckError) as error:
                create_deck(self.collection, name)
            self.assertEqual(error.exception.code, "name")
            self.assertNotIn("Private", str(error.exception))
        self.assertEqual(self.collection.decks.calls, [])
        self.assertEqual(validate_deck_name("Synthetic::Biology"), "Synthetic::Biology")

    def test_existing_case_insensitive_or_filtered_name_is_not_created(self):
        for name in ("synthetic::biology", "Synthetic filtered deck"):
            with self.subTest(name=name), self.assertRaises(DeckError) as error:
                create_deck(self.collection, name)
            self.assertEqual(error.exception.code, "exists")
        self.assertFalse(any(call[0] == "create" for call in self.collection.decks.calls))

    def test_stable_id_and_name_validation_regressions_turn_tests_red(self):
        mutations = (
            ("services/decks.py", "deck.deck_id == target.deck_id",
             "deck.name == target.name",
             "test_decks.DeckTests.test_rename_retains_id_and_deleted_name_reuse_never_redirects"),
            ("services/decks.py", "name = validate_deck_name(name)", "name = name",
             "test_decks.DeckTests.test_invalid_names_do_not_touch_collection"),
        )
        for relative, before, after, selector in mutations:
            with self.subTest(selector=selector), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "addon"
                shutil.copytree(support.ROOT, copied, ignore=shutil.ignore_patterns("__pycache__"))
                source = copied / relative
                text = source.read_text()
                self.assertIn(before, text)
                source.write_text(text.replace(before, after, 1))
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", selector],
                    cwd=copied / "tests",
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("FAILED", result.stderr)


if __name__ == "__main__":
    unittest.main()
