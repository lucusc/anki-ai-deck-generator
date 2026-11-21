import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import support
from addon.models.audience import Audience, AudienceError, AudienceSelection, AudienceSettings


class AudienceTests(unittest.TestCase):
    def test_all_options_serialize_exact_wire_values_and_review_labels(self):
        expected = [
            ("middle_school", "Middle School"), ("high_school", "High School"),
            ("university", "University"), ("certification", "Certification"),
            ("professional", "Professional"),
        ]
        self.assertEqual([(item.value, item.label) for item in Audience], expected)
        for wire, label in expected:
            with self.subTest(audience=wire):
                snapshot = AudienceSettings.from_mapping({"audience": wire})
                self.assertEqual(snapshot.to_mapping(), {"audience": wire})
                self.assertEqual(snapshot.review_label, "Audience: " + label)
                self.assertNotIn(wire, repr(snapshot))

    def test_missing_unknown_and_non_string_values_fail_without_coercion(self):
        with self.assertRaises(AudienceError) as error:
            AudienceSettings.from_mapping({})
        self.assertEqual(error.exception.code, "missing")
        for value in (
            None, "", "Middle School", "HIGH_SCHOOL", "university ", " university",
            "private-study-content", 0, 1, True, [], {}, Audience.UNIVERSITY,
        ):
            with self.subTest(value=value), self.assertRaises(AudienceError) as error:
                AudienceSettings.from_mapping({"audience": value})
            self.assertEqual(error.exception.code, "invalid")
            self.assertNotIn("private", str(error.exception))
        for payload in (None, [], "university", False):
            with self.subTest(payload=payload), self.assertRaises(AudienceError):
                AudienceSettings.from_mapping(payload)
        for value in (None, "university", [], True):
            with self.subTest(constructor=value), self.assertRaises(AudienceError):
                AudienceSettings(value)
        with self.assertRaises(TypeError):
            AudienceSettings()

    def test_snapshot_is_detached_from_input_output_and_later_selection(self):
        source = {"audience": "university", "future_setting": ["synthetic"]}
        snapshot = AudienceSettings.from_mapping(source)
        source["audience"] = "professional"
        output = snapshot.to_mapping()
        output["audience"] = "high_school"
        with self.assertRaises(FrozenInstanceError):
            snapshot.audience = Audience.PROFESSIONAL
        selection = AudienceSelection(snapshot)
        selection.choose("middle_school")
        self.assertEqual(snapshot.to_mapping(), {"audience": "university"})
        self.assertEqual(snapshot.review_label, "Audience: University")
        self.assertEqual(selection.capture().to_mapping(), {"audience": "middle_school"})
        self.assertEqual(snapshot.to_mapping(), {"audience": "university"})

    def test_selection_has_no_default_and_invalid_choice_cannot_reuse_old_audience(self):
        selection = AudienceSelection()
        with self.assertRaises(AudienceError) as error:
            selection.capture()
        self.assertEqual(error.exception.code, "missing")
        selection.choose("university")
        captured = selection.capture()
        with self.assertRaises(AudienceError) as error:
            selection.choose("private-study-content")
        self.assertEqual(error.exception.code, "invalid")
        with self.assertRaises(AudienceError):
            selection.capture()
        self.assertIsNone(selection.settings)
        self.assertEqual(captured.review_label, "Audience: University")

    def test_no_default_validation_and_snapshot_regressions_turn_tests_red(self):
        mutations = (
            ("models/audience.py", 'raise AudienceError("missing")',
             'return cls(Audience.UNIVERSITY)',
             "test_audience.AudienceTests.test_missing_unknown_and_non_string_values_fail_without_coercion"),
            ("models/audience.py", 'raise AudienceError("invalid") from None',
             "return cls(Audience.UNIVERSITY)",
             "test_audience.AudienceTests.test_missing_unknown_and_non_string_values_fail_without_coercion"),
            ("models/audience.py", "@dataclass(frozen=True, repr=False)",
             "@dataclass(frozen=False, repr=False)",
             "test_audience.AudienceTests.test_snapshot_is_detached_from_input_output_and_later_selection"),
            ("ui/audience.py", "selected_index = -1", "selected_index = 0",
             "test_load.LoadTests.test_audience_requires_explicit_choice_and_snapshot_survives_ui_changes"),
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
                self.assertIn("AssertionError", result.stderr)
                self.assertIn("FAILED", result.stderr)


if __name__ == "__main__":
    unittest.main()
