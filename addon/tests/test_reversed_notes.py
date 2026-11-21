import copy
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import support
from addon.models.deck import DeckError, DeckIdentity
from addon.models.note_payload import NoteMappingError
from addon.services.basic_notes import import_approved_basic
from addon.services.note_models import map_generated_note, model_name
from addon.services.reversed_notes import (
    ReversedImportError, capture_reversed_target, import_approved_reversed,
)
from test_basic_notes import ImportCollection
from test_note_models import payload


class ReversedBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.col = ImportCollection()
        self.target = capture_reversed_target(self.col, DeckIdentity(101, "Synthetic::Biology"))
        self.col.decks.calls.clear()
        self.col.find_notes = lambda _: []

    def test_approval_and_budget_validation_precede_collection_access(self):
        for approved in (False, None, 0, 1, "yes"):
            with self.subTest(approved=approved), self.assertRaises(ReversedImportError) as error:
                import_approved_reversed(
                    self.col, payload("reversed"), self.target,
                    approved=approved, remaining_cards=2, create_model=True,
                )
            self.assertEqual(error.exception.code, "approval")
        for budget in (None, True, False, -1, 2.0, "2", [], object()):
            with self.subTest(budget=budget), self.assertRaises(ReversedImportError) as error:
                import_approved_reversed(
                    self.col, payload("reversed"), self.target,
                    approved=True, remaining_cards=budget, create_model=True,
                )
            self.assertEqual(error.exception.code, "budget")
        with self.assertRaises(TypeError):
            import_approved_reversed(self.col, payload("reversed"), self.target, approved=True)
        self.assertEqual(self.col.decks.calls, [])
        self.assertEqual(self.col.models.calls, [])
        self.assertEqual(self.col.saved_notes, [])

    def test_wrong_family_model_permission_and_collection_fail_before_writes(self):
        for family in ("basic", "cloze"):
            with self.subTest(family=family), self.assertRaises(ReversedImportError) as error:
                import_approved_reversed(
                    self.col, payload(family), self.target, approved=True,
                    remaining_cards=2, create_model=True,
                )
            self.assertEqual(error.exception.code, "family")
        with self.assertRaises(NoteMappingError) as error:
            import_approved_reversed(
                self.col, payload("reversed"), self.target, approved=True,
                remaining_cards=2, create_model=1,
            )
        self.assertEqual(error.exception.field, "create_model")
        with self.assertRaises(ReversedImportError) as error:
            import_approved_reversed(
                ImportCollection(), payload("reversed"), self.target,
                approved=True, remaining_cards=2, create_model=True,
            )
        self.assertEqual(error.exception.code, "lifetime")
        self.assertEqual(self.col.decks.calls, [])
        self.assertEqual(self.col.models.calls, [])
        self.assertEqual(self.col.saved_notes, [])

    def test_one_remaining_card_is_not_enough_for_one_reversed_note(self):
        for budget in (0, 1):
            with self.subTest(budget=budget), self.assertRaises(ReversedImportError) as error:
                import_approved_reversed(
                    self.col, payload("reversed"), self.target,
                    approved=True, remaining_cards=budget, create_model=True,
                )
            self.assertEqual(error.exception.code, "limit")
        self.assertEqual(self.col.models.calls, [])
        self.assertEqual(self.col.new_notes, [])
        self.assertEqual(self.col.saved_notes, [])


@unittest.skipUnless(importlib.util.find_spec("anki"), "Anki core is not installed")
class RealAnkiReversedTests(unittest.TestCase):
    def setUp(self):
        from anki.collection import Collection
        from anki.lang import set_lang

        set_lang("en_US")
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "collection.anki2")
        self.col = Collection(self.path)
        self.deck_id = self.col.decks.add_normal_deck_with_name("Synthetic::Destination").id
        self.target = capture_reversed_target(
            self.col, DeckIdentity(self.deck_id, "Synthetic::Destination"),
        )
        self.raw = payload("reversed")
        self.raw["fields"] = {
            "Front": '<b onclick="bad()">Question?</b>',
            "Back": "<i>Answer</i> &amp; detail",
        }

    def tearDown(self):
        self.col.close()
        self.directory.cleanup()

    def run_import(self, raw=None, budget=2, **kwargs):
        return import_approved_reversed(
            self.col, self.raw if raw is None else raw, self.target, approved=True,
            remaining_cards=budget, create_model=True, **kwargs,
        )

    def assert_faces(self, note):
        cards = sorted(note.cards(), key=lambda card: card.ord)
        self.assertEqual([(card.ord, card.nid, card.did) for card in cards],
                         [(0, note.id, self.deck_id), (1, note.id, self.deck_id)])
        front, back = "<b>Question?</b>", "<i>Answer</i> &amp; detail"
        self.assertIn(front, cards[0].question())
        self.assertNotIn(back, cards[0].question())
        self.assertIn(back, cards[1].question())
        self.assertNotIn(front, cards[1].question())
        for card in cards:
            self.assertIn(front, card.answer())
            self.assertIn(back, card.answer())
            self.assertIn("Synthetic.txt", card.answer())
            self.assertNotIn("onclick", card.question() + card.answer())
            self.assertNotIn(self.raw["import_id"], card.question() + card.answer())

    def test_saved_directions_counts_and_retry_survive_reopen(self):
        self.col.decks.rename(self.deck_id, "Synthetic::Renamed")
        result = self.run_import()
        self.assertEqual((result.note_count, result.card_count), (1, 2))
        self.assertEqual((result.added_note_count, result.added_card_count), (1, 2))
        self.assertEqual(result.note_changes.count, 2)
        self.assertEqual(len(set(result.card_ids)), 2)
        self.assertEqual(result.deck, DeckIdentity(self.deck_id, "Synthetic::Renamed"))
        self.assertTrue(result.changes.note)
        self.assertTrue(result.changes.card)
        self.assertTrue(result.changes.notetype)
        self.assertFalse(result.reused)
        self.assert_faces(self.col.get_note(result.note_id))
        self.col.close()
        from anki.collection import Collection

        self.col = Collection(self.path)
        with self.assertRaises(ReversedImportError) as error:
            self.run_import()
        self.assertEqual(error.exception.code, "lifetime")
        self.target = capture_reversed_target(self.col, result.deck)
        prior = self.col.get_note(result.note_id)
        self.assertEqual(prior["Import ID"], self.raw["import_id"])
        self.assert_faces(prior)
        with patch.object(self.col, "add_note", side_effect=AssertionError("retry must not insert")):
            retry = self.run_import(budget=0)
        self.assertEqual((retry.note_id, retry.card_ids), (result.note_id, result.card_ids))
        self.assertEqual((retry.note_count, retry.card_count), (1, 2))
        self.assertEqual((retry.added_note_count, retry.added_card_count), (0, 0))
        self.assertTrue(retry.reused)
        self.assertIsNone(retry.note_changes)
        self.assertIsNone(retry.model_changes)
        self.assertEqual(retry.changes.ListFields(), [])
        self.assertEqual(len(self.col.find_notes("")), 1)

    def test_budget_is_enforced_at_insertion_and_tracks_only_new_cards(self):
        for budget in (0, 1):
            with self.subTest(budget=budget), self.assertRaises(ReversedImportError) as error:
                self.run_import(budget=budget)
            self.assertEqual(error.exception.code, "limit")
            self.assertEqual(self.col.find_notes(""), [])
            self.assertIsNone(self.col.models.by_name(model_name("reversed")))
        remaining = 3
        first = self.run_import(budget=remaining)
        remaining -= first.added_card_count
        second = copy.deepcopy(self.raw)
        second["import_id"] = "33333333-3333-4333-8333-333333333333"
        with self.assertRaises(ReversedImportError) as error:
            self.run_import(second, budget=remaining)
        self.assertEqual(error.exception.code, "limit")
        self.assertEqual(remaining, 1)
        self.assertEqual(len(self.col.find_cards("")), 2)
        self.assertEqual(self.run_import(budget=remaining).added_card_count, 0)

    def test_changed_content_provenance_or_source_conflicts_without_writes(self):
        first = self.run_import()
        changed_notes = []
        for field in ("Front", "Back"):
            raw = copy.deepcopy(self.raw)
            raw["fields"][field] = "Edited after first import"
            changed_notes.append(raw)
        for key in ("prompt_version", "model_version"):
            raw = copy.deepcopy(self.raw)
            raw[key] = "synthetic-v2"
            changed_notes.append(raw)
        raw = copy.deepcopy(self.raw)
        raw["source"]["location"]["page"] = 3
        changed_notes.append(raw)
        for raw in changed_notes:
            with self.subTest(raw=raw), self.assertRaises(ReversedImportError) as error:
                self.run_import(raw, budget=0)
            self.assertEqual(error.exception.code, "identity")
        self.assertEqual(len(self.col.find_notes("")), 1)
        self.assertEqual(self.col.get_note(first.note_id)["Back"], "<i>Answer</i> &amp; detail")
        equivalent = copy.deepcopy(self.raw)
        equivalent["fields"]["Front"] = "<b>Question?</b>"
        self.assertTrue(self.run_import(equivalent, budget=0).reused)

    def test_foreign_family_duplicate_identity_and_changed_destination_conflict(self):
        basic = copy.deepcopy(self.raw)
        basic["model_family"] = "basic"
        import_approved_basic(self.col, basic, self.target, approved=True, create_model=True)
        with self.assertRaises(ReversedImportError) as error:
            self.run_import()
        self.assertEqual(error.exception.code, "identity")
        self.assertIsNone(self.col.models.by_name(model_name("reversed")))
        self.col.remove_notes(self.col.find_notes(""))
        first = self.run_import()
        other_id = self.col.decks.add_normal_deck_with_name("Other").id
        self.target = capture_reversed_target(self.col, DeckIdentity(other_id, "Other"))
        with self.assertRaises(ReversedImportError) as error:
            self.run_import(budget=0)
        self.assertEqual(error.exception.code, "cards")
        self.target = capture_reversed_target(self.col, first.deck)
        duplicate = map_generated_note(self.col, self.raw, first.deck)
        self.col.add_note(duplicate.note, self.deck_id)
        with self.assertRaises(ReversedImportError) as error:
            self.run_import(budget=0)
        self.assertEqual(error.exception.code, "identity")
        self.assertEqual(len(self.col.find_notes("")), 2)

    def test_user_edits_and_missing_direction_are_not_matching_retries(self):
        first = self.run_import()
        note = self.col.get_note(first.note_id)
        note["Back"] = "User edit"
        self.col.update_note(note)
        with self.assertRaises(ReversedImportError) as error:
            self.run_import()
        self.assertEqual(error.exception.code, "identity")
        note["Back"] = "<i>Answer</i> &amp; detail"
        self.col.update_note(note)
        self.col.remove_cards_and_orphaned_notes([first.card_ids[1]])
        with self.assertRaises(ReversedImportError) as error:
            self.run_import()
        self.assertEqual(error.exception.code, "cards")
        self.assertEqual(len(self.col.find_cards("")), 1)

    def test_custom_builtin_is_untouched_and_managed_customizations_fail(self):
        builtin = self.col.models.by_name("Basic (and reversed card)")
        self.assertIsNotNone(builtin)
        builtin["tmpls"][0]["qfmt"] = "Synthetic custom question {{Front}}"
        self.col.models.update_dict(builtin)
        before = copy.deepcopy(self.col.models.get(builtin["id"]))
        first = self.run_import()
        self.assertEqual(self.col.models.get(builtin["id"]), before)
        self.assert_faces(self.col.get_note(first.note_id))
        managed = self.col.models.by_name(model_name("reversed"))
        for customize in (
            lambda model: model["tmpls"][1].update(qfmt="{{#Front}}{{Back}}{{/Front}}"),
            lambda model: model["tmpls"][0].update(bqfmt="Custom browser {{Front}}"),
            lambda model: model["tmpls"][0].update(did=self.deck_id),
            lambda model: model.update(css=model["css"] + "\n.card { color: red; }"),
        ):
            model = copy.deepcopy(managed)
            customize(model)
            self.col.models.update_dict(model)
            saved = copy.deepcopy(self.col.models.get(model["id"]))
            with self.assertRaises(NoteMappingError) as error:
                self.run_import(budget=0)
            self.assertEqual(error.exception.code, "model_collision")
            self.assertEqual(self.col.models.get(model["id"]), saved)
            self.assertEqual(len(self.col.find_notes("")), 1)
            self.col.models.update_dict(copy.deepcopy(managed))

    def test_format_only_fields_fail_and_stripped_hidden_attributes_render(self):
        for field in ("Front", "Back"):
            for content in ("", "<b></b>", "<br>", "<div> </div>", "&nbsp;", "&#8203;", "\u200b"):
                raw = copy.deepcopy(self.raw)
                raw["fields"][field] = content
                with self.subTest(field=field, content=content), self.assertRaises(
                    (NoteMappingError, ReversedImportError)
                ):
                    self.run_import(raw)
                self.assertEqual(self.col.find_notes(""), [])
        raw = copy.deepcopy(self.raw)
        raw["fields"] = {
            "Front": '<span style="display:none">Question?</span>',
            "Back": '<div hidden="hidden">Answer</div>',
        }
        result = self.run_import(raw)
        cards = self.col.get_note(result.note_id).cards()
        self.assertEqual(len(cards), 2)
        self.assertIn("<span>Question?</span>", cards[0].question())
        self.assertIn("<div>Answer</div>", cards[1].question())
        self.assertNotIn("hidden", cards[1].answer())
        self.assertEqual(len(self.col.get_empty_cards().notes), 0)

    def test_visible_mixed_format_text_and_zwj_emoji_are_preserved(self):
        raw = copy.deepcopy(self.raw)
        front = "<b>Q\u200b?</b>"
        back = "\U0001f469\u200d\U0001f4bb"
        raw["fields"] = {"Front": front, "Back": back}
        result = self.run_import(raw)
        note = self.col.get_note(result.note_id)
        self.assertEqual(note["Front"], front)
        self.assertEqual(note["Back"], back)
        cards = sorted(note.cards(), key=lambda card: card.ord)
        self.assertEqual(len(cards), 2)
        self.assertIn(front, cards[0].question())
        self.assertIn(back, cards[1].question())
        self.assertIn(back, cards[0].answer())
        self.assertIn(front, cards[1].answer())
        self.assertTrue(self.run_import(raw, budget=0).reused)

    def test_core_generation_is_not_a_template_count_for_empty_or_custom_questions(self):
        # Deliberately bypass the importer with synthetic notes to characterize Anki.
        mapped = map_generated_note(self.col, self.raw, self.target.deck, create_model=True)
        mapped.note["Front"] = ""
        changes = self.col.add_note(mapped.note, self.deck_id)
        cards = mapped.note.cards()
        self.assertEqual(changes.count, 1)
        self.assertEqual([(card.ord, card.nid) for card in cards], [(1, mapped.note.id)])
        self.assertIn("<i>Answer</i>", cards[0].question())
        self.assertNotIn("<b>Question?</b>", cards[0].answer())

        for content in ("<b></b>", "&nbsp;"):
            probe = map_generated_note(self.col, self.raw, self.target.deck)
            probe.note["Front"] = content
            self.assertEqual(self.col.add_note(probe.note, self.deck_id).count, 2)
            probe_cards = sorted(probe.note.cards(), key=lambda card: card.ord)
            self.assertEqual(len(probe_cards), 2)
            self.assertEqual(probe_cards[0].render_output().question_text, content)
            self.assertIn("<i>Answer</i>", probe_cards[1].question())
            self.col.remove_notes([probe.note.id])
        mapped.note["Front"] = "\u200b"
        self.col.update_note(mapped.note)
        cards = sorted(mapped.note.cards(), key=lambda card: card.ord)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0].render_output().question_text, "\u200b")
        self.assertIn("<i>Answer</i>", cards[1].question())
        with self.assertRaises(ReversedImportError) as error:
            raw = copy.deepcopy(self.raw)
            raw["fields"]["Front"] = "\u200b"
            self.run_import(raw, budget=0)
        self.assertEqual(error.exception.code, "render")

        builtin = self.col.models.by_name("Basic (and reversed card)")
        builtin["tmpls"][0]["qfmt"] = "{{#Front}}{{Front}}{{/Front}}"
        builtin["tmpls"][1]["qfmt"] = "{{#Front}}{{Back}}{{/Front}}"
        self.col.models.update_dict(builtin)
        custom = self.col.new_note(builtin)
        custom["Front"] = ""
        custom["Back"] = "Synthetic answer"
        added = self.col.add_note(custom, self.deck_id)
        self.assertEqual(added.count, 1)
        custom_cards = custom.cards()
        self.assertEqual(len(custom_cards), 1)
        self.assertIn("front of this card is blank", custom_cards[0].question().lower())
        self.assertIn("front of this card is blank", custom_cards[0].answer().lower())

    def test_removed_filtered_destination_and_snapshot_mutation(self):
        original = copy.deepcopy(self.raw)

        def mutate_then_map(collection, value, target, *, create_model):
            self.raw["fields"]["Back"] = "Changed caller object"
            return map_generated_note(collection, value, target, create_model=create_model)

        with patch("addon.services.reversed_notes.map_generated_note", side_effect=mutate_then_map):
            result = self.run_import()
        self.assertEqual(self.col.get_note(result.note_id)["Back"], original["fields"]["Back"])
        self.col.decks.remove([self.deck_id])
        with self.assertRaises(DeckError):
            self.run_import()
        filtered_id = self.col.decks.new_filtered("Synthetic filtered")
        self.target = type(self.target)(self.col, DeckIdentity(filtered_id, "Synthetic filtered"))
        with self.assertRaises(DeckError):
            self.run_import()

    def test_ambiguous_post_commit_failure_can_be_reconciled_without_reinsertion(self):
        real_add = self.col.add_note

        def save_then_fail(note, deck_id):
            real_add(note, deck_id)
            raise RuntimeError("synthetic lost acknowledgement")

        with patch.object(self.col, "add_note", side_effect=save_then_fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic lost acknowledgement"):
                self.run_import()
        self.assertEqual(len(self.col.find_notes("")), 1)
        retry = self.run_import(budget=0)
        self.assertTrue(retry.reused)
        self.assert_faces(self.col.get_note(retry.note_id))
        self.assertEqual(len(self.col.find_cards("")), 2)

    def test_failed_insert_is_not_success_and_post_write_mutation_is_explicit(self):
        with patch.object(self.col, "add_note", side_effect=RuntimeError("synthetic outage")):
            with self.assertRaisesRegex(RuntimeError, "synthetic outage"):
                self.run_import()
        self.assertEqual(self.col.find_notes(""), [])
        self.assertIsNotNone(self.col.models.by_name(model_name("reversed")))
        real_add = self.col.add_note

        def mutate_then_add(note, deck_id):
            note["Back"] = "Unapproved hook change"
            return real_add(note, deck_id)

        with patch.object(self.col, "add_note", side_effect=mutate_then_add):
            with self.assertRaises(ReversedImportError) as error:
                self.run_import()
        self.assertEqual(error.exception.code, "saved_state")
        with self.assertRaises(ReversedImportError) as error:
            self.run_import()
        self.assertEqual(error.exception.code, "identity")
        self.assertEqual(len(self.col.find_notes("")), 1)

    def test_source_mutations_break_budget_and_retry_boundaries(self):
        mutations = (
            ("if prior is None and remaining_cards < 2:", "if False:",
             "test_reversed_notes.RealAnkiReversedTests.test_budget_is_enforced_at_insertion_and_tracks_only_new_cards"),
            ('collection.find_notes(f\'"Import ID:{import_id}"\')', "[]",
             "test_reversed_notes.RealAnkiReversedTests.test_saved_directions_counts_and_retry_survive_reopen"),
        )
        for before, after, selector in mutations:
            with self.subTest(selector=selector), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "addon"
                shutil.copytree(support.ROOT, copied, ignore=shutil.ignore_patterns("__pycache__"))
                source = copied / "services" / "reversed_notes.py"
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


if __name__ == "__main__":
    unittest.main()
