import copy
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import support
from addon.models.deck import DeckError, DeckIdentity
from addon.models.note_payload import NoteMappingError
from addon.services.basic_notes import (
    BasicImportError, capture_basic_target, import_approved_basic,
)
from addon.services.note_models import map_generated_note, model_name
from test_note_models import SyntheticCollection, payload


class Changes:
    def __init__(self, **flags):
        self.flags = flags

    def MergeFrom(self, other):
        self.flags.update(other.flags)


class ImportCollection(SyntheticCollection):
    def __init__(self):
        super().__init__()
        self.saved_notes = []
        original_add = self.models.add_dict

        def add_model(model):
            result = original_add(model)
            result.changes = Changes(notetype=True)
            return result

        self.models.add_dict = add_model

    def add_note(self, note, deck_id):
        note.id = len(self.saved_notes) + 1
        self.saved_notes.append((note, deck_id))
        return types.SimpleNamespace(changes=Changes(note=True, card=True), count=1)


class BasicImportTests(unittest.TestCase):
    def setUp(self):
        self.col = ImportCollection()
        self.target = capture_basic_target(self.col, DeckIdentity(101, "Synthetic::Biology"))
        self.col.decks.calls.clear()

    def test_explicit_approval_is_required_before_any_collection_access(self):
        for approved in (False, None, 0, 1, "yes", [], object()):
            with self.subTest(approved=approved), self.assertRaises(BasicImportError) as error:
                import_approved_basic(self.col, payload(), self.target, approved=approved, create_model=True)
            self.assertEqual(error.exception.code, "approval")
        self.assertEqual(self.col.decks.calls, [])
        self.assertEqual(self.col.models.calls, [])
        self.assertEqual(self.col.new_notes, [])
        self.assertEqual(self.col.saved_notes, [])

    def test_basic_saved_to_captured_renamed_deck_with_changes_and_sanitized_fields(self):
        self.col.decks.names[101] = "Synthetic::Renamed"
        raw = payload()
        raw["fields"]["Front"] = '<b onclick="bad()">Unit?</b>'
        raw["source"]["name"] = "<img> [sound:x]"
        result = import_approved_basic(self.col, raw, self.target, approved=True, create_model=True)
        note, deck_id = self.col.saved_notes[0]
        self.assertEqual((result.note_id, deck_id), (note.id, 101))
        self.assertEqual(result.deck, DeckIdentity(101, "Synthetic::Renamed"))
        self.assertEqual(note.fields["Front"], "<b>Unit?</b>")
        self.assertEqual(note.fields["Back"], "A cell.")
        self.assertEqual(note.fields["Source"], "&lt;img&gt; &#91;sound:x&#93;; page: 2; section: Chapter 1")
        self.assertEqual(note.fields["Import ID"], raw["import_id"])
        self.assertEqual(result.changes.flags, {"note": True, "card": True, "notetype": True})
        self.assertIsNotNone(result.model_changes)
        later = import_approved_basic(self.col, payload(), self.target, approved=True)
        self.assertIsNone(later.model_changes)
        self.assertEqual(later.changes.flags, {"note": True, "card": True})

    def test_other_families_invalid_payload_and_markup_do_not_write(self):
        cases = [
            (payload("reversed"), BasicImportError, "family"),
            (payload("cloze"), BasicImportError, "family"),
            ({**payload(), "schema_version": 2}, NoteMappingError, "version"),
            ({**payload(), "fields": {"Front": "<script>x</script>", "Back": "x"}},
             NoteMappingError, "markup"),
        ]
        for raw, exception, code in cases:
            with self.subTest(code=code), self.assertRaises(exception) as error:
                import_approved_basic(self.col, raw, self.target, approved=True, create_model=True)
            self.assertEqual(error.exception.code, code)
        self.assertEqual(self.col.models.calls, [])
        self.assertEqual(self.col.new_notes, [])
        self.assertEqual(self.col.saved_notes, [])

    def test_import_uses_validated_snapshot_even_if_review_object_changes(self):
        raw = payload()
        original = copy.deepcopy(raw)

        def mutate_then_map(collection, value, target, *, create_model):
            raw["model_family"] = "reversed"
            raw["fields"]["Back"] = "Changed after capture"
            raw["source"]["name"] = "Changed source"
            return map_generated_note(collection, value, target, create_model=create_model)

        with patch("addon.services.basic_notes.map_generated_note", side_effect=mutate_then_map):
            import_approved_basic(self.col, raw, self.target, approved=True, create_model=True)
        note, _ = self.col.saved_notes[0]
        self.assertEqual(note.fields["Back"], original["fields"]["Back"])
        self.assertTrue(note.fields["Source"].startswith(original["source"]["name"]))
        self.assertEqual(self.col.models.saved[note.model_id]["name"], model_name("basic"))

    def test_removed_filtered_reused_or_different_collection_cannot_receive_note(self):
        del self.col.decks.names[101]
        self.col.decks.names[404] = "Synthetic::Biology"
        for deck_id in (101, 303):
            captured = self.target if deck_id == 101 else type(self.target)(
                self.col, DeckIdentity(303, "Synthetic filtered deck")
            )
            with self.subTest(deck_id=deck_id), self.assertRaises(DeckError) as error:
                import_approved_basic(self.col, payload(), captured, approved=True, create_model=True)
            self.assertEqual(error.exception.code, "missing")
        other = ImportCollection()
        with self.assertRaises(BasicImportError) as error:
            import_approved_basic(other, payload(), self.target, approved=True, create_model=True)
        self.assertEqual(error.exception.code, "lifetime")
        self.assertEqual(other.decks.calls, [])
        self.assertEqual(other.models.calls, [])
        self.assertEqual(self.col.models.calls, [])

    def test_capture_requires_numeric_identity_and_existing_normal_deck(self):
        for target in (DeckIdentity(True, "x"), DeckIdentity(0, "x"),
                       DeckIdentity("101", "x"), DeckIdentity(101, None), "101"):
            with self.subTest(target=target), self.assertRaises(BasicImportError):
                capture_basic_target(self.col, target)
        with self.assertRaises(DeckError):
            capture_basic_target(self.col, None)
        with self.assertRaises(DeckError):
            capture_basic_target(self.col, DeckIdentity(303, "Synthetic filtered deck"))
        forged = type(self.target)(self.col, DeckIdentity(True, "Default"))
        with self.assertRaises(BasicImportError):
            import_approved_basic(self.col, payload(), forged, approved=True, create_model=True)
        self.assertEqual(self.col.models.calls, [])

    def test_model_permission_and_storage_failure_are_explicit(self):
        with self.assertRaises(NoteMappingError) as error:
            import_approved_basic(self.col, payload(), self.target, approved=True)
        self.assertEqual(error.exception.code, "model_missing")
        with self.assertRaises(NoteMappingError) as error:
            import_approved_basic(self.col, payload(), self.target, approved=True, create_model=1)
        self.assertEqual(error.exception.field, "create_model")
        self.col.add_note = lambda *_: (_ for _ in ()).throw(RuntimeError("synthetic outage"))
        with self.assertRaisesRegex(RuntimeError, "synthetic outage"):
            import_approved_basic(self.col, payload(), self.target, approved=True, create_model=True)
        self.assertEqual(len(self.col.models.saved), 1)
        self.assertEqual(self.col.saved_notes, [])

    def test_source_mutations_break_approval_and_family_boundaries(self):
        mutations = (
            ("if approved is not True:", "if False:",
             "test_basic_notes.BasicImportTests.test_explicit_approval_is_required_before_any_collection_access"),
            ('if payload.model_family != "basic" or not isinstance(payload.fields, BasicFields):',
             "if False:",
             "test_basic_notes.BasicImportTests.test_other_families_invalid_payload_and_markup_do_not_write"),
        )
        for before, after, selector in mutations:
            with self.subTest(selector=selector), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "addon"
                shutil.copytree(support.ROOT, copied, ignore=shutil.ignore_patterns("__pycache__"))
                source = copied / "services" / "basic_notes.py"
                text = source.read_text()
                self.assertIn(before, text)
                source.write_text(text.replace(before, after, 1))
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", selector], cwd=copied / "tests",
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("FAILED", result.stderr)


@unittest.skipUnless(importlib.util.find_spec("anki"), "Anki core is not installed")
class RealAnkiBasicImportTests(unittest.TestCase):
    def test_approved_save_and_render_survive_collection_restart(self):
        from anki.collection import Collection

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "collection.anki2")
            col = Collection(path)
            try:
                deck_id = col.decks.add_normal_deck_with_name("Synthetic::Destination").id
                target = capture_basic_target(col, DeckIdentity(deck_id, "Synthetic::Destination"))
                col.decks.rename(deck_id, "Synthetic::Renamed")
                raw = payload()
                raw["fields"] = {
                    "Front": '<b onclick="bad()">Question?</b>',
                    "Back": "<i>Answer</i> &amp; detail",
                }
                raw["source"]["name"] = "<script>synthetic</script> [sound:x]"
                with self.assertRaises(BasicImportError):
                    import_approved_basic(col, raw, target, approved=False, create_model=True)
                self.assertEqual(col.find_notes(""), [])
                self.assertIsNone(col.models.by_name(model_name("basic")))
                result = import_approved_basic(col, raw, target, approved=True, create_model=True)
                self.assertTrue(result.changes.note)
                self.assertTrue(result.changes.notetype)
                self.assertEqual(result.note_changes.count, 1)
                self.assertEqual(result.deck, DeckIdentity(deck_id, "Synthetic::Renamed"))
                note_id = result.note_id
            finally:
                col.close()

            col = Collection(path)
            try:
                note = col.get_note(note_id)
                cards = note.cards()
                self.assertEqual(len(cards), 1)
                self.assertEqual(cards[0].did, deck_id)
                self.assertEqual(note["Front"], "<b>Question?</b>")
                self.assertEqual(note["Back"], "<i>Answer</i> &amp; detail")
                self.assertEqual(note["Import ID"], raw["import_id"])
                self.assertEqual(note["Payload Version"], "1")
                question, answer = cards[0].question(), cards[0].answer()
                self.assertIn("<b>Question?</b>", question)
                self.assertNotIn("Answer", question)
                self.assertIn("<i>Answer</i> &amp; detail", answer)
                self.assertIn("&lt;script&gt;synthetic&lt;/script&gt;", answer)
                self.assertNotIn("<script>", answer)
                self.assertNotIn("[sound:x]", answer)
                self.assertNotIn("onclick", question + answer)
                with self.assertRaises(BasicImportError) as error:
                    import_approved_basic(col, payload(), target, approved=True, create_model=True)
                self.assertEqual(error.exception.code, "lifetime")
                self.assertEqual(len(col.find_notes("")), 1)
            finally:
                col.close()

    def test_deleted_deck_and_reused_name_never_receive_an_import(self):
        from anki.collection import Collection

        with tempfile.TemporaryDirectory() as directory:
            col = Collection(str(Path(directory) / "collection.anki2"))
            try:
                deck_id = col.decks.add_normal_deck_with_name("Synthetic target").id
                target = capture_basic_target(col, DeckIdentity(deck_id, "Synthetic target"))
                col.decks.remove([deck_id])
                time.sleep(0.02)
                replacement = col.decks.add_normal_deck_with_name("Synthetic target").id
                self.assertNotEqual(deck_id, replacement)
                with self.assertRaises(DeckError) as error:
                    import_approved_basic(col, payload(), target, approved=True, create_model=True)
                self.assertEqual(error.exception.code, "missing")
                self.assertEqual(col.find_notes(""), [])
                self.assertIsNone(col.models.by_name(model_name("basic")))
            finally:
                col.close()


if __name__ == "__main__":
    unittest.main()
