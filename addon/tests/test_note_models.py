import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from html import unescape
from pathlib import Path

import support
from addon.models.deck import DeckError, DeckIdentity
from addon.models.note_payload import BasicFields, ClozeFields, NoteMappingError, parse_generated_note
from addon.services.note_models import map_generated_note, model_name


IMPORT_ID = "11111111-1111-4111-8111-111111111111"
DOCUMENT_ID = "22222222-2222-4222-8222-222222222222"


def payload(family="basic"):
    return {
        "schema_version": 1, "model_family": family, "import_id": IMPORT_ID,
        "fields": ({"Text": "{{c1::<b>cell</b>::structure}} stores {{c2::DNA}}", "Back Extra": ""}
                   if family == "cloze" else {"Front": "<b>Unit?</b>", "Back": "A cell."}),
        "source": {
            "document_id": DOCUMENT_ID, "sha256": "a" * 64, "name": "Synthetic.txt",
            "location": {"page": 2, "slide": None, "section": "Chapter 1"},
        },
        "prompt_version": "synthetic-v1", "model_version": "synthetic-model-v1",
    }


class SyntheticModels:
    """Supported public API double; not real Anki persistence/render evidence."""
    def __init__(self):
        self.saved = {}
        self.calls = []

    def by_name(self, name):
        self.calls.append(("lookup", name))
        return next((model for model in self.saved.values()
                     if model["name"].casefold() == name.casefold()), None)

    def new(self, name):
        self.calls.append(("new", name))
        return {"id": 0, "name": name, "type": 0, "flds": [], "tmpls": [], "css": "", "sortf": 0}

    def new_field(self, name):
        return {"name": name, "ord": None}

    def add_field(self, model, field):
        model["flds"].append(field)

    def new_template(self, name):
        return {"name": name, "ord": None, "qfmt": "", "afmt": ""}

    def add_template(self, model, template):
        model["tmpls"].append(template)

    def add_dict(self, model):
        self.calls.append(("add", model["name"]))
        model = copy.deepcopy(model)
        model["id"] = max(self.saved, default=100) + 1
        for key in ("flds", "tmpls"):
            for index, item in enumerate(model[key]):
                item["ord"] = index
        self.saved[model["id"]] = model
        return types.SimpleNamespace(id=model["id"], changes=types.SimpleNamespace(notetype=True))

    def get(self, model_id):
        self.calls.append(("get", model_id))
        return self.saved.get(model_id)


class SyntheticNote:
    def __init__(self, model):
        self.model_id = model["id"]
        self.fields = dict.fromkeys((field["name"] for field in model["flds"]), "")
        self.id = 0

    def __setitem__(self, key, value):
        if key not in self.fields:
            raise KeyError(key)
        self.fields[key] = value


class SyntheticCollection:
    def __init__(self):
        self.models = SyntheticModels()
        self.decks = support.SyntheticDecks()
        self.new_notes = []

    def new_note(self, model):
        note = SyntheticNote(model)
        self.new_notes.append(note)
        return note


class NoteModelTests(unittest.TestCase):
    def setUp(self):
        self.collection = SyntheticCollection()
        self.target = DeckIdentity(101, "Synthetic::Biology")

    def test_map_all_families_exact_fields_templates_and_no_note_insertion(self):
        for family in ("basic", "reversed", "cloze"):
            with self.subTest(family=family):
                result = map_generated_note(self.collection, payload(family), self.target, create_model=True)
                model = self.collection.models.saved[result.note.model_id]
                self.assertEqual(model["name"], model_name(family))
                self.assertEqual(model["type"], 1 if family == "cloze" else 0)
                self.assertEqual(result.deck.deck_id, 101)
                self.assertEqual(result.note.id, 0)
                self.assertTrue(result.model_changes.changes.notetype)
                self.assertEqual(result.note.fields["Import ID"], IMPORT_ID)
                self.assertEqual(result.note.fields["Payload Version"], "1")
                self.assertEqual(result.note.fields["Source"], "Synthetic.txt; page: 2; section: Chapter 1")
                if family == "cloze":
                    self.assertEqual(result.note.fields["Text"], "{{c1::<b>cell</b>::structure}} stores {{c2::DNA}}")
                    self.assertEqual(result.note.fields["Back Extra"], "")
                    self.assertEqual(model["tmpls"][0]["qfmt"], "{{cloze:Text}}")
                    self.assertIn("{{cloze:Text}}", model["tmpls"][0]["afmt"])
                else:
                    self.assertEqual(result.note.fields["Front"], "<b>Unit?</b>")
                    self.assertEqual(result.note.fields["Back"], "A cell.")
                    self.assertEqual(model["tmpls"][0]["qfmt"], "{{Front}}")
                    self.assertIn("{{Back}}", model["tmpls"][0]["afmt"])
                    if family == "reversed":
                        self.assertEqual(model["tmpls"][1]["qfmt"], "{{Back}}")
                        self.assertIn("{{Front}}", model["tmpls"][1]["afmt"])
                self.assertEqual(len(model["tmpls"]), 2 if family == "reversed" else 1)
                for template in model["tmpls"]:
                    self.assertIn("{{Source}}", template["afmt"])
                    self.assertNotIn("Import ID", template["afmt"])
                self.assertEqual(
                    set(result.note.fields),
                    ({"Text", "Back Extra"} if family == "cloze" else {"Front", "Back"})
                    | {"Source", "Import ID", "Payload Version", "Provenance"},
                )

    def test_persistent_identity_provenance_safe_names_and_reuse_after_service_restart(self):
        raw = payload()
        raw["source"]["name"] = '<script>synthetic</script> [sound:a] {{c99::x}}'
        raw["source"]["location"]["section"] = 'A "section" & <img>'
        raw["fields"]["Front"] = '<b onclick="bad()" style="display:none">Unit?</b>'
        first = map_generated_note(self.collection, raw, self.target, create_model=True)
        saved_fields = copy.deepcopy(first.note.fields)
        self.assertEqual(first.note.fields["Front"], "<b>Unit?</b>")
        self.assertNotIn("<script>", saved_fields["Source"])
        self.assertNotIn("[sound:", saved_fields["Source"])
        self.assertNotIn("{{c99", saved_fields["Source"])
        metadata = json.loads(unescape(saved_fields["Provenance"]))
        self.assertEqual(metadata["source"]["document_id"], DOCUMENT_ID)
        self.assertEqual(metadata["source"]["sha256"], "a" * 64)
        self.assertEqual(metadata["source"]["name"], raw["source"]["name"])
        self.assertEqual(metadata["source"]["location"]["page"], 2)
        self.assertEqual(metadata["prompt_version"], "synthetic-v1")
        self.assertEqual(metadata["model_version"], "synthetic-model-v1")
        self.assertEqual(metadata["model_family"], "basic")
        later_collection = SyntheticCollection()
        later_collection.models.saved = copy.deepcopy(self.collection.models.saved)
        second = map_generated_note(later_collection, raw, self.target)
        self.assertIsNone(second.model_changes)
        self.assertEqual(second.note.model_id, first.note.model_id)
        self.assertEqual(saved_fields["Import ID"], second.note.fields["Import ID"])
        self.assertFalse(any(call[0] == "add" for call in later_collection.models.calls))
        self.assertNotIn("synthetic", repr(parse_generated_note(raw)))
        self.assertNotIn("synthetic", repr(second))

    def test_customized_builtins_and_other_user_models_are_never_touched(self):
        self.collection.models.saved[99] = {
            "id": 99, "name": "Basic", "type": 0, "css": "custom",
            "flds": [{"name": "My Question", "ord": 0}],
            "tmpls": [{"name": "Custom", "qfmt": "{{My Question}}", "afmt": "custom"}],
        }
        original = copy.deepcopy(self.collection.models.saved[99])
        map_generated_note(self.collection, payload(), self.target, create_model=True)
        self.assertEqual(self.collection.models.saved[99], original)
        self.assertFalse(any(call == ("lookup", "Basic") for call in self.collection.models.calls))

    def test_managed_model_customization_collision_and_invalid_fields_fail_without_overwrite(self):
        first = map_generated_note(self.collection, payload(), self.target, create_model=True)
        original = copy.deepcopy(self.collection.models.saved[first.note.model_id])
        for mutate, code in (
            (lambda m: m["flds"][0].update(name="Customized"), "model_fields"),
            (lambda m: m["flds"].append({"name": "Extra", "ord": 6}), "model_fields"),
            (lambda m: m["flds"][0].update(ord=2), "model_fields"),
            (lambda m: m.update(flds=None), "model_fields"),
            (lambda m: m.update(type=1), "model_collision"),
            (lambda m: m.update(css="custom"), "model_collision"),
            (lambda m: m["tmpls"][0].update(qfmt="<script>secret</script>"), "model_collision"),
            (lambda m: m["tmpls"][0].update(afmt="{{Back}}"), "model_collision"),
            (lambda m: m["tmpls"][0].update(ord=3), "model_collision"),
            (lambda m: m["tmpls"][0].update(did=404), "model_collision"),
            (lambda m: m["tmpls"][0].update(bqfmt="<script>secret</script>"), "model_collision"),
            (lambda m: m["tmpls"][0].update(bafmt="{{Back}}"), "model_collision"),
            (lambda m: m.update(name=model_name("basic").upper()), "model_collision"),
            (lambda m: m.update(tmpls=[]), "model_collision"),
        ):
            with self.subTest(code=code):
                modified = copy.deepcopy(original)
                mutate(modified)
                self.collection.models.saved[first.note.model_id] = modified
                before = copy.deepcopy(self.collection.models.saved)
                self.collection.models.calls.clear()
                with self.assertRaises(NoteMappingError) as error:
                    map_generated_note(self.collection, payload(), self.target, create_model=True)
                self.assertEqual(error.exception.code, code)
                self.assertEqual(self.collection.models.saved, before)
                self.assertFalse(any(call[0] == "add" for call in self.collection.models.calls))

    def test_creation_is_explicit_and_collection_errors_are_not_success(self):
        with self.assertRaises(NoteMappingError) as error:
            map_generated_note(self.collection, payload(), self.target)
        self.assertEqual(error.exception.code, "model_missing")
        self.assertEqual(self.collection.models.saved, {})
        with self.assertRaises(NoteMappingError) as error:
            map_generated_note(self.collection, payload(), self.target, create_model="false")
        self.assertEqual(error.exception.field, "create_model")
        self.assertEqual(self.collection.models.saved, {})
        with self.assertRaises(NoteMappingError) as error:
            map_generated_note(None, payload(), self.target, create_model=True)
        self.assertEqual(error.exception.code, "collection")
        self.collection.models.add_dict = lambda model: (_ for _ in ()).throw(RuntimeError("outage"))
        with self.assertRaisesRegex(RuntimeError, "outage"):
            map_generated_note(self.collection, payload(), self.target, create_model=True)
        self.assertEqual(self.collection.new_notes, [])

    def test_deleted_filtered_or_renamed_deck_preserves_stable_identity(self):
        self.collection.decks.names[101] = "Synthetic::Renamed"
        result = map_generated_note(self.collection, payload(), self.target, create_model=True)
        self.assertEqual(result.deck, DeckIdentity(101, "Synthetic::Renamed"))
        del self.collection.decks.names[101]
        self.collection.decks.names[404] = self.target.name
        for target in (self.target, DeckIdentity(303, "Synthetic filtered deck"), None):
            with self.subTest(target=target), self.assertRaises(DeckError):
                map_generated_note(self.collection, payload(), target, create_model=True)
        self.assertEqual(len(self.collection.new_notes), 1)

    def test_malformed_payloads_versions_fields_identity_and_source_fail_before_collection(self):
        cases = []
        for key, value in (
            ("schema_version", 2), ("schema_version", True), ("schema_version", "1"),
            ("model_family", "Basic"), ("model_family", []), ("fields", {"Front": "x"}),
            ("fields", {"Front": "", "Back": "x"}), ("fields", {"Front": True, "Back": "x"}),
            ("import_id", "not-an-id"), ("import_id", IMPORT_ID.upper().replace("1", "A")),
            ("prompt_version", "<script>"), ("model_version", "x" * 65),
        ):
            raw = payload()
            raw[key] = value
            cases.append(raw)
        for key in payload():
            raw = payload()
            del raw[key]
            cases.append(raw)
        raw = payload()
        raw["unknown"] = "secret"
        cases.append(raw)
        for key, value in (
            ("name", "private\nname"), ("document_id", "bad"), ("sha256", "A" * 64),
            ("location", {"page": True, "slide": None, "section": None}),
            ("location", {"page": 0, "slide": None, "section": None}),
            ("location", {"page": 1, "slide": -2, "section": None}),
            ("location", {"page": None, "slide": None, "section": ""}),
            ("location", {}),
        ):
            raw = payload()
            raw["source"][key] = value
            cases.append(raw)
        for raw in [None, [], {}, *cases]:
            with self.subTest(raw=raw), self.assertRaises(NoteMappingError):
                map_generated_note(self.collection, raw, self.target, create_model=True)
        self.assertEqual(self.collection.models.calls, [])
        self.assertEqual(self.collection.decks.calls, [])
        self.assertEqual(self.collection.new_notes, [])
        self.assertIsInstance(parse_generated_note(payload()).fields, BasicFields)
        self.assertIsInstance(parse_generated_note(payload("cloze")).fields, ClozeFields)

    def test_size_boundaries_and_document_level_location(self):
        raw = payload()
        raw["fields"]["Front"] = "x" * 32768
        raw["source"]["name"] = "n" * 255
        raw["source"]["location"] = {"page": None, "slide": None, "section": None}
        result = map_generated_note(self.collection, raw, self.target, create_model=True)
        self.assertEqual(result.note.fields["Front"], "x" * 32768)
        self.assertEqual(result.note.fields["Source"], "n" * 255)
        for path in ("field", "source"):
            invalid = copy.deepcopy(raw)
            if path == "field":
                invalid["fields"]["Front"] += "x"
            else:
                invalid["source"]["name"] += "n"
            with self.subTest(path=path), self.assertRaises(NoteMappingError) as error:
                map_generated_note(self.collection, invalid, self.target)
            self.assertEqual(error.exception.code, "field")

    def test_markup_and_cloze_errors_include_fixed_field_path_before_collection_access(self):
        for raw, field, code in (
            ({**payload(), "fields": {"Front": "<script>secret</script>", "Back": "x"}}, "fields.Front", "markup"),
            ({**payload(), "fields": {"Front": "<br>", "Back": "x"}}, "fields.Front", "field"),
            ({**payload("cloze"), "fields": {"Text": "{{c0::x}}", "Back Extra": ""}}, "fields.Text", "cloze"),
            ({**payload("cloze"), "fields": {"Text": "{{c1::x}}", "Back Extra": "[sound:a]"}}, "fields.Back Extra", "markup"),
        ):
            with self.subTest(field=field), self.assertRaises(NoteMappingError) as error:
                map_generated_note(self.collection, raw, self.target, create_model=True)
            self.assertEqual(error.exception.field, field)
            self.assertEqual(error.exception.code, code)
            self.assertNotIn("secret", str(error.exception))
        self.assertEqual(self.collection.models.calls, [])
        self.assertEqual(self.collection.decks.calls, [])

    def test_real_source_mutations_break_identity_sanitization_and_model_protection_assertions(self):
        mutations = (
            ("services/note_models.py", '"Import ID": payload.import_id', '"Import ID": ""',
             "test_note_models.NoteModelTests.test_map_all_families_exact_fields_templates_and_no_note_insertion"),
            ("services/note_models.py", "_validate_model(model, family)", "pass",
             "test_note_models.NoteModelTests.test_managed_model_customization_collision_and_invalid_fields_fail_without_overwrite"),
            ("services/markup.py", 'self.parts.append(f"<{tag}>")',
             'self.parts.append(self.get_starttag_text())',
             "test_markup.MarkupTests.test_canonical_safe_formatting_without_attributes_or_urls"),
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
                    [sys.executable, "-m", "unittest", selector], cwd=copied / "tests",
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("FAILED", result.stderr)


if __name__ == "__main__":
    unittest.main()
