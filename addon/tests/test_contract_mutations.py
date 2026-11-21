"""Prove focused assertions reject regressions in isolated real source copies."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support


class ContractMutationTests(unittest.TestCase):
    def test_security_and_responsiveness_assertions_turn_red(self):
        mutations = [
            (
                "services/oauth.py",
                "store.write(tokens.refresh_token)",
                "pass",
                "test_auth.AuthTests.test_failed_protected_write_never_accepts_access_token",
            ),
            (
                "services/oauth.py",
                "or not isinstance(methods, list) or \"S256\" not in methods",
                "or False",
                "test_auth.AuthTests.test_mismatched_issuer_insecure_endpoints_and_missing_pkce_fail_closed",
            ),
            (
                "ui/signin.py",
                ".without_collection()",
                "",
                "test_load.LoadTests.test_dialog_modeless_worker_dispatch_single_window_and_profile_cancel",
            ),
        ]
        for relative, before, after, selector in mutations:
            with self.subTest(mutation=relative + ":" + selector), tempfile.TemporaryDirectory() as directory:
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
