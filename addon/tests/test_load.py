import importlib.util
import json
import sys
import tempfile
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZipFile

import support
from test_auth import CONFIG


class Signal:
    def __init__(self):
        self.callbacks = []

    def emit(self, *args):
        for callback in self.callbacks:
            callback(*args)


class Widget:
    def __init__(self, *args):
        self.main_thread = threading.get_ident()
        self.clicked = Signal()
        self.triggered = Signal()
        self.text = args[0] if args and isinstance(args[0], str) else ""
        self.enabled = True
        self.visible = False
        self.name = ""

    def setText(self, text):
        if threading.get_ident() != self.main_thread:
            raise AssertionError("Qt text updated off main thread")
        self.text = text

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setObjectName(self, name):
        self.name = name

    def objectName(self):
        return self.name

    def setWindowTitle(self, title):
        pass

    def setAttribute(self, attr):
        pass

    def setWordWrap(self, wrap):
        pass

    def setTextFormat(self, fmt):
        pass

    def show(self):
        self.visible = True

    def raise_(self):
        pass

    def activateWindow(self):
        pass

    def reject(self):
        self.visible = False

    def closeEvent(self, event):
        self.visible = False

    def addWidget(self, widget):
        pass


class Menu:
    def __init__(self):
        self.items = []

    def actions(self):
        return self.items

    def addAction(self, action):
        self.items.append(action)


class Query:
    pending = []

    def __init__(self, *, parent, op, success):
        self.op = op
        self.success = success
        self.no_collection = False

    def without_collection(self):
        self.no_collection = True
        return self

    def failure(self, callback):
        self.on_failure = callback
        return self

    def run_in_background(self):
        self.pending.append(self)

    def finish(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.op, None)
            try:
                result = future.result(timeout=3)
            except Exception as error:
                self.on_failure(error)
            else:
                self.success(result)


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.menu = Menu()
        self.warning = Mock()
        self.hooks = types.SimpleNamespace(profile_will_close=[], main_window_did_init=[])
        self.mw = types.SimpleNamespace(
            form=types.SimpleNamespace(menuTools=self.menu),
            addonManager=types.SimpleNamespace(getConfig=Mock(return_value=dict(CONFIG))),
            pm=types.SimpleNamespace(name="Synthetic profile"),
        )
        self.version = types.ModuleType("anki.buildinfo")
        self.version.version = "25.09"
        qt = types.ModuleType("aqt.qt")
        for name in ("QAction", "QDialog", "QLabel", "QPushButton", "QVBoxLayout"):
            setattr(qt, name, Widget)
        qt.Qt = types.SimpleNamespace(
            WidgetAttribute=types.SimpleNamespace(WA_DeleteOnClose=1),
            TextFormat=types.SimpleNamespace(PlainText=1),
        )
        qt.qconnect = lambda signal, callback: signal.callbacks.append(callback)
        aqt = types.ModuleType("aqt")
        aqt.mw, aqt.gui_hooks = self.mw, self.hooks
        utils = types.ModuleType("aqt.utils")
        utils.showWarning = self.warning
        operations = types.ModuleType("aqt.operations")
        operations.QueryOp = Query
        self.modules = {
            "anki": types.ModuleType("anki"), "anki.buildinfo": self.version,
            "aqt": aqt, "aqt.qt": qt, "aqt.utils": utils, "aqt.operations": operations,
        }
        self.patcher = patch.dict(sys.modules, self.modules)
        self.patcher.start()
        Query.pending.clear()
        self.packages = []

    def tearDown(self):
        self.patcher.stop()
        for name in list(sys.modules):
            if any(name == prefix or name.startswith(prefix + ".") for prefix in self.packages):
                del sys.modules[name]

    def load(self, root=support.ROOT):
        name = f"synthetic_anki_addon_{len(self.packages)}"
        self.packages.append(name)
        spec = importlib.util.spec_from_file_location(
            name, root / "__init__.py", submodule_search_locations=[str(root)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        spec.loader.exec_module(package)
        return package, sys.modules[name + ".ui.bootstrap"]

    def test_packaged_entry_point_loads_once_and_exposes_menu_on_each_target(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "foundation.ankiaddon"
            support.load_build().build(archive)
            with ZipFile(archive) as package:
                names = set(package.namelist())
                self.assertIn("__init__.py", names)
                self.assertIn("ui/signin.py", names)
                self.assertIn("services/oauth.py", names)
                self.assertIn("services/credentials.py", names)
                self.assertFalse(any(name.startswith(("tests/", "tools/")) for name in names))
                self.assertEqual(json.loads(package.read("config.json"))["issuer"], "")
                extracted = Path(directory) / "unpacked"
                package.extractall(extracted)
            for version in ("25.09", "26.09.4"):
                with self.subTest(version=version):
                    self.version.version = version
                    self.menu.items.clear()
                    self.hooks.profile_will_close.clear()
                    _, bootstrap = self.load(extracted)
                    self.assertEqual(len(self.menu.items), 1)
                    self.assertEqual(self.menu.items[0].text, "Anki AI Deck Generator...")
                    bootstrap.install(bootstrap.__package__.split(".")[0])
                    self.assertEqual(len(self.menu.items), 1)
                    self.assertEqual(len(self.hooks.profile_will_close), 1)
                    self.warning.assert_not_called()
                    # Loading must not read profile/config/credentials or make requests.
                    self.mw.addonManager.getConfig.assert_not_called()
                    self.assertEqual(Query.pending, [])

    def test_unconfigured_and_unsupported_startup_are_actionable_and_no_network(self):
        _, bootstrap = self.load()
        self.mw.addonManager.getConfig.return_value = {"issuer": ""}
        self.menu.items[0].triggered.emit(False)
        self.assertIn("Configure issuer", self.warning.call_args.args[0])
        self.assertIsNone(bootstrap._controller.dialog)
        self.menu.items.clear()
        self.version.version = "26.11b1"
        self.load()
        self.assertEqual(len(self.hooks.main_window_did_init), 1)
        self.hooks.main_window_did_init[0]()
        self.assertIn("25.09 and 26.09.4", self.warning.call_args.args[0])
        self.assertEqual(Query.pending, [])

    def test_dialog_modeless_worker_dispatch_single_window_and_profile_cancel(self):
        _, bootstrap = self.load()
        self.menu.items[0].triggered.emit()
        dialog = bootstrap._controller.dialog
        self.assertTrue(dialog.visible)
        self.menu.items[0].triggered.emit()
        self.assertIs(bootstrap._controller.dialog, dialog)
        worker_threads = []
        dialog.session.sign_in = lambda: worker_threads.append(threading.get_ident())
        dialog.signin.clicked.emit()
        self.assertTrue(dialog.busy)
        self.assertFalse(dialog.signin.enabled)
        self.assertEqual(worker_threads, [])
        self.assertEqual(len(Query.pending), 1)
        self.assertTrue(Query.pending[0].no_collection)
        dialog.signin.clicked.emit()
        self.assertEqual(len(Query.pending), 1)
        Query.pending[0].finish()
        self.assertNotEqual(worker_threads, [threading.get_ident()])
        self.assertIn("Signed in", dialog.status.text)
        self.assertFalse(dialog.busy)
        self.hooks.profile_will_close[0]()
        self.assertTrue(dialog.session.cancel.is_set())
        self.assertFalse(dialog.active)
        self.assertIsNone(bootstrap._controller.dialog)

    def test_background_private_exception_is_sanitized_and_late_callbacks_ignored(self):
        self.load()
        self.menu.items[0].triggered.emit()
        bootstrap = sys.modules[self.packages[-1] + ".ui.bootstrap"]
        dialog = bootstrap._controller.dialog

        def fail():
            raise RuntimeError("private-token-and-study-content")

        dialog.session.sign_in = fail
        dialog.signin.clicked.emit()
        Query.pending[-1].finish()
        self.assertNotIn("private", dialog.status.text)
        self.assertIn("error code internal", dialog.status.text)
        dialog.signin.clicked.emit()
        dialog.reject()
        old_status = dialog.status.text
        Query.pending[-1].finish()
        self.assertEqual(dialog.status.text, old_status)
        dialog.reject = Mock(side_effect=RuntimeError("already-deleted-Qt-object"))
        self.hooks.profile_will_close[0]()
        dialog.reject.assert_not_called()

    def test_startup_error_is_not_a_raw_traceback(self):
        self.modules["aqt.qt"].QAction = Mock(side_effect=RuntimeError("private-config"))
        self.load()
        self.assertIn("could not start", self.warning.call_args.args[0])
        self.assertNotIn("private", self.warning.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
