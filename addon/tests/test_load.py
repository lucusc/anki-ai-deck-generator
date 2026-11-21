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

    def setPlaceholderText(self, text):
        self.placeholder = text


class LineEdit(Widget):
    def __init__(self, *args):
        super().__init__(*args)
        del self.text
        self.value = ""

    def text(self):
        return self.value

    def setText(self, text):
        self.value = text

    def clear(self):
        self.value = ""


class ComboBox(Widget):
    def __init__(self, *args):
        super().__init__(*args)
        self.currentIndexChanged = Signal()
        self.items = []
        self.index = -1
        self.blocked = False

    def blockSignals(self, blocked):
        self.blocked = blocked

    def addItem(self, name, data):
        self.items.append((name, data))
        if self.index == -1:
            self.setCurrentIndex(0)

    def clear(self):
        self.items.clear()
        self.setCurrentIndex(-1)

    def setCurrentIndex(self, index):
        self.index = index
        if not self.blocked:
            self.currentIndexChanged.emit(index)

    def itemData(self, index):
        return self.items[index][1] if 0 <= index < len(self.items) else None


class Menu:
    def __init__(self):
        self.items = []

    def actions(self):
        return self.items

    def addAction(self, action):
        self.items.append(action)


class Query:
    pending = []
    collection = None

    def __init__(self, *, parent, op, success):
        self.op = op
        self.on_success = success
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
            future = pool.submit(self.op, None if self.no_collection else self.collection)
            try:
                result = future.result(timeout=3)
            except Exception as error:
                self.on_failure(error)
            else:
                self.on_success(result)


class CollectionQuery(Query):
    def __init__(self, parent, op):
        super().__init__(parent=parent, op=op, success=None)

    def success(self, callback):
        self.on_success = callback
        return self


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.menu = Menu()
        self.warning = Mock()
        self.hooks = types.SimpleNamespace(profile_will_close=[], main_window_did_init=[])
        self.mw = types.SimpleNamespace(
            form=types.SimpleNamespace(menuTools=self.menu),
            addonManager=types.SimpleNamespace(getConfig=Mock(return_value=dict(CONFIG))),
            pm=types.SimpleNamespace(name="Synthetic profile"),
            col=types.SimpleNamespace(decks=support.SyntheticDecks()),
        )
        self.version = types.ModuleType("anki.buildinfo")
        self.version.version = "25.09"
        qt = types.ModuleType("aqt.qt")
        for name in ("QAction", "QDialog", "QLabel", "QPushButton", "QVBoxLayout", "QWidget"):
            setattr(qt, name, Widget)
        qt.QLineEdit = LineEdit
        qt.QComboBox = ComboBox
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
        operations.CollectionOp = CollectionQuery
        self.modules = {
            "anki": types.ModuleType("anki"), "anki.buildinfo": self.version,
            "aqt": aqt, "aqt.qt": qt, "aqt.utils": utils, "aqt.operations": operations,
        }
        self.patcher = patch.dict(sys.modules, self.modules)
        self.patcher.start()
        Query.pending.clear()
        Query.collection = self.mw.col
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
                self.assertTrue({"models/deck.py", "services/decks.py", "ui/decks.py"} <= names)
                self.assertTrue({"models/audience.py", "ui/audience.py"} <= names)
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
        self.assertEqual(len(Query.pending), 1)
        self.assertFalse(Query.pending[0].no_collection)
        Query.pending.pop(0).finish()
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
        Query.pending.pop(0).finish()

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

    def open_ready(self):
        _, bootstrap = self.load()
        self.menu.items[0].triggered.emit()
        dialog = bootstrap._controller.dialog
        self.assertEqual(self.mw.col.decks.calls, [])
        Query.pending.pop(0).finish()
        return bootstrap, dialog

    def test_deck_selection_rename_deletion_and_dialog_reopen_keep_stable_identity(self):
        bootstrap, dialog = self.open_ready()
        selector = dialog.decks
        self.assertIsNone(bootstrap._controller.selection.target)
        self.assertEqual(selector.combo.index, -1)
        index = next(index for index, (_, did) in enumerate(selector.combo.items) if did == 101)
        selector.combo.setCurrentIndex(index)
        target = bootstrap._controller.selection.target
        self.assertEqual(target.deck_id, 101)
        self.assertFalse(any(call[0] == "create" for call in self.mw.col.decks.calls))
        self.mw.col.decks.names[101] = "Synthetic renamed"
        selector.refresh_button.clicked.emit()
        Query.pending.pop(0).finish()
        self.assertEqual(bootstrap._controller.selection.target.deck_id, target.deck_id)
        self.assertEqual(bootstrap._controller.selection.target.name, "Synthetic renamed")
        self.assertIn("renamed", selector.status.text)
        self.assertEqual(selector.combo.items[selector.combo.index], ("Synthetic renamed", 101))
        dialog.reject()
        self.menu.items[0].triggered.emit()
        reopened = bootstrap._controller.dialog
        Query.pending.pop(0).finish()
        self.assertIsNot(reopened, dialog)
        self.assertEqual(reopened.decks.combo.items[reopened.decks.combo.index][1], 101)
        del self.mw.col.decks.names[101]
        self.mw.col.decks.names[404] = "Synthetic renamed"
        reopened.decks.refresh_button.clicked.emit()
        Query.pending.pop(0).finish()
        self.assertEqual(reopened.decks.combo.index, -1)
        self.assertEqual(bootstrap._controller.selection.target.deck_id, 101)
        self.assertIn("deleted", reopened.decks.status.text)
        self.assertIn("no fallback", reopened.decks.status.text)
        self.hooks.profile_will_close[0]()
        self.assertIsNone(bootstrap._controller.selection.target)

    def test_user_directed_creation_runs_collection_op_and_validates_names(self):
        bootstrap, dialog = self.open_ready()
        selector = dialog.decks
        self.mw.col.decks.calls.clear()
        selector.name.setText("Invalid::")
        selector.create_button.clicked.emit()
        self.assertEqual(Query.pending, [])
        self.assertEqual(self.mw.col.decks.calls, [])
        self.assertIn("Enter a deck name", selector.status.text)
        selector.name.setText("Synthetic::Chemistry")
        self.assertEqual(Query.pending, [])
        selector.create_button.clicked.emit()
        self.assertTrue(selector.busy)
        self.assertFalse(dialog.signin.enabled)
        self.assertFalse(selector.create_button.enabled)
        self.assertEqual(self.mw.col.decks.calls, [])
        self.assertIsInstance(Query.pending[0], CollectionQuery)
        self.assertFalse(Query.pending[0].no_collection)
        dialog.signin.clicked.emit()
        self.assertEqual(len(Query.pending), 1)
        Query.pending.pop(0).finish()
        self.assertEqual(self.mw.col.decks.calls,
                         [("lookup", "Synthetic::Chemistry"), ("create", "Synthetic::Chemistry")])
        self.assertEqual(bootstrap._controller.selection.target.deck_id, 304)
        Query.pending.pop(0).finish()
        self.assertEqual(selector.combo.items[selector.combo.index], ("Synthetic::Chemistry", 304))
        self.assertEqual(selector.name.text(), "")
        selector.name.setText("synthetic::chemistry")
        selector.create_button.clicked.emit()
        Query.pending.pop(0).finish()
        self.assertIn("already exists", selector.status.text)
        self.assertEqual(sum(call[0] == "create" for call in self.mw.col.decks.calls), 1)

    def test_auth_worker_never_overlaps_selector_collection_dispatch(self):
        _, dialog = self.open_ready()
        selector = dialog.decks
        self.mw.col.decks.calls.clear()
        dialog.session.sign_in = Mock()
        dialog.signin.clicked.emit()
        self.assertFalse(selector.combo.enabled)
        self.assertFalse(selector.create_button.enabled)
        selector.refresh_button.clicked.emit()
        selector.name.setText("Synthetic new deck")
        selector.create_button.clicked.emit()
        self.assertEqual(len(Query.pending), 1)
        self.assertTrue(Query.pending[0].no_collection)
        Query.pending.pop(0).finish()
        dialog.session.sign_in.assert_called_once_with()
        self.assertEqual(self.mw.col.decks.calls, [])
        self.assertTrue(selector.create_button.enabled)
        selector.refresh_button.clicked.emit()
        Query.pending.pop(0).finish()
        self.assertEqual(self.mw.col.decks.calls, [("list", False, False)])

    def test_profile_close_cancels_queued_creation_and_late_read_callbacks(self):
        bootstrap, dialog = self.open_ready()
        selector = dialog.decks
        selector.name.setText("Synthetic cancelled")
        selector.create_button.clicked.emit()
        self.mw.col.decks.calls.clear()
        self.hooks.profile_will_close[0]()
        status = selector.status.text
        Query.pending.pop(0).finish()
        self.assertEqual(self.mw.col.decks.calls, [])
        self.assertEqual(selector.status.text, status)
        self.assertIsNone(bootstrap._controller.selection.target)
        self.assertTrue(dialog.session.cancel.is_set())
        self.menu.items[0].triggered.emit()
        reopened = bootstrap._controller.dialog
        operation = Query.pending.pop(0)
        operation.op = lambda collection: [types.SimpleNamespace(deck_id=101, name="Synthetic late")]
        self.hooks.profile_will_close[0]()
        operation.finish()
        self.assertEqual(reopened.decks.combo.items, [])
        self.assertIsNone(bootstrap._controller.selection.target)

    def test_collection_failure_is_content_free_and_controls_recover(self):
        _, dialog = self.open_ready()
        self.mw.col.decks.all_names_and_ids = Mock(
            side_effect=RuntimeError("private deck name and study content")
        )
        with self.assertLogs("anki_ai_deck_generator", level="INFO") as logs:
            dialog.decks.refresh_button.clicked.emit()
            Query.pending.pop(0).finish()
        self.assertIn("error code internal", dialog.decks.status.text)
        self.assertNotIn("private", dialog.decks.status.text)
        self.assertNotIn("private", " ".join(logs.output))
        self.assertFalse(dialog.decks.busy)
        self.assertTrue(dialog.signin.enabled)
        self.assertTrue(dialog.decks.refresh_button.enabled)

    def test_close_during_started_creation_keeps_committed_deck_but_ignores_selection(self):
        bootstrap, dialog = self.open_ready()
        selector = dialog.decks
        selector.name.setText("Synthetic committed")
        selector.create_button.clicked.emit()
        original = self.mw.col.decks.add_normal_deck_with_name

        def close_during_write(name):
            selector.close_selector()
            return original(name)

        self.mw.col.decks.add_normal_deck_with_name = close_during_write
        Query.pending.pop(0).finish()
        self.assertIn("Synthetic committed", self.mw.col.decks.names.values())
        self.assertIsNone(bootstrap._controller.selection.target)
        self.assertEqual(Query.pending, [])
        dialog.closeEvent(None)
        self.assertFalse(dialog.active)
        self.assertTrue(dialog.session.cancel.is_set())

    def test_packaged_selector_workflow_on_both_target_api_doubles(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "selector.ankiaddon"
            support.load_build().build(archive)
            extracted = Path(directory) / "unpacked"
            with ZipFile(archive) as package:
                package.extractall(extracted)
            for version in ("25.09", "26.09.4"):
                with self.subTest(version=version):
                    self.version.version = version
                    self.menu.items.clear()
                    self.hooks.profile_will_close.clear()
                    _, bootstrap = self.load(extracted)
                    self.menu.items[0].triggered.emit()
                    dialog = bootstrap._controller.dialog
                    Query.pending.pop(0).finish()
                    self.assertEqual(len(self.menu.items), 1)
                    self.assertEqual({did for _, did in dialog.decks.combo.items}, {1, 101, 202})
                    dialog.decks.combo.setCurrentIndex(1)
                    self.assertEqual(bootstrap._controller.selection.target.deck_id, 101)
                    self.hooks.profile_will_close[0]()

    def test_audience_requires_explicit_choice_and_snapshot_survives_ui_changes(self):
        bootstrap, dialog = self.open_ready()
        selector = dialog.audience
        contract = sys.modules[self.packages[-1] + ".models.audience"]
        self.assertEqual(selector.combo.index, -1)
        self.assertEqual(selector.combo.items, [
            ("Middle School", "middle_school"), ("High School", "high_school"),
            ("University", "university"), ("Certification", "certification"),
            ("Professional", "professional"),
        ])
        with self.assertRaises(contract.AudienceError) as error:
            selector.capture_settings()
        self.assertEqual(error.exception.code, "missing")
        self.mw.col.decks.calls.clear()
        for index, (label, wire) in enumerate(selector.combo.items):
            selector.combo.setCurrentIndex(index)
            snapshot = selector.capture_settings()
            self.assertEqual(snapshot.to_mapping(), {"audience": wire})
            self.assertEqual(selector.status.text, "Audience: " + label)
        captured = selector.capture_settings()
        dialog.decks.combo.setCurrentIndex(1)
        target = bootstrap._controller.selection.target
        selector.combo.setCurrentIndex(0)
        self.assertEqual(captured.to_mapping(), {"audience": "professional"})
        self.assertEqual(captured.review_label, "Audience: Professional")
        self.assertEqual(selector.capture_settings().to_mapping(), {"audience": "middle_school"})
        self.assertEqual(bootstrap._controller.selection.target, target)
        self.assertEqual(Query.pending, [])
        self.assertEqual(self.mw.col.decks.calls, [])
        selector.combo.items.append(("Private invalid value", "private-study-content"))
        selector.combo.setCurrentIndex(5)
        self.assertNotIn("private", selector.status.text)
        with self.assertRaises(contract.AudienceError):
            selector.capture_settings()
        self.assertIsNone(bootstrap._controller.audience_selection.settings)
        selector.combo.setCurrentIndex(2)
        selector.combo.setCurrentIndex(-1)
        with self.assertRaises(contract.AudienceError):
            selector.capture_settings()

    def test_audience_lifetime_reopen_profile_close_and_closed_callbacks(self):
        bootstrap, dialog = self.open_ready()
        selector = dialog.audience
        contract = sys.modules[self.packages[-1] + ".models.audience"]
        selector.combo.setCurrentIndex(2)
        captured = selector.capture_settings()
        dialog.reject()
        self.assertFalse(selector.combo.enabled)
        selector.select(4)
        with self.assertRaises(contract.AudienceError) as error:
            selector.capture_settings()
        self.assertEqual(error.exception.code, "closed")
        self.menu.items[0].triggered.emit()
        reopened = bootstrap._controller.dialog
        Query.pending.pop(0).finish()
        self.assertEqual(reopened.audience.combo.index, 2)
        self.assertEqual(reopened.audience.status.text, "Audience: University")
        self.hooks.profile_will_close[0]()
        self.assertIsNone(bootstrap._controller.audience_selection.settings)
        reopened.audience.select(4)
        self.assertIsNone(bootstrap._controller.audience_selection.settings)
        self.assertEqual(captured.review_label, "Audience: University")
        self.menu.items[0].triggered.emit()
        self.assertEqual(bootstrap._controller.dialog.audience.combo.index, -1)
        Query.pending.pop(0).finish()

    def test_audience_controls_follow_existing_auth_and_deck_busy_lifecycle(self):
        _, bootstrap = self.load()
        self.menu.items[0].triggered.emit()
        dialog = bootstrap._controller.dialog
        self.assertFalse(dialog.audience.combo.enabled)
        dialog.audience.select(2)
        self.assertIsNone(bootstrap._controller.audience_selection.settings)
        Query.pending.pop(0).finish()
        self.assertTrue(dialog.audience.combo.enabled)
        dialog.audience.combo.setCurrentIndex(2)
        captured = dialog.audience.capture_settings()
        dialog.session.sign_in = Mock(side_effect=RuntimeError("private-auth-error"))
        dialog.signin.clicked.emit()
        self.assertFalse(dialog.audience.combo.enabled)
        dialog.audience.select(0)
        self.assertEqual(dialog.audience.capture_settings(), captured)
        Query.pending.pop(0).finish()
        self.assertTrue(dialog.audience.combo.enabled)
        dialog.session.sign_in = Mock()
        dialog.signin.clicked.emit()
        Query.pending.pop(0).finish()
        self.assertTrue(dialog.audience.combo.enabled)
        self.mw.col.decks.all_names_and_ids = Mock(side_effect=RuntimeError("private-deck"))
        dialog.decks.refresh_button.clicked.emit()
        self.assertFalse(dialog.audience.combo.enabled)
        Query.pending.pop(0).finish()
        self.assertTrue(dialog.audience.combo.enabled)
        dialog.closeEvent(None)
        self.assertFalse(dialog.audience.combo.enabled)
        self.assertTrue(dialog.audience.closed)

    def test_packaged_audience_workflow_on_both_target_api_doubles(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "audience.ankiaddon"
            support.load_build().build(archive)
            extracted = Path(directory) / "unpacked"
            with ZipFile(archive) as package:
                package.extractall(extracted)
            for version in ("25.09", "26.09.4"):
                with self.subTest(version=version):
                    self.version.version = version
                    self.menu.items.clear()
                    self.hooks.profile_will_close.clear()
                    _, bootstrap = self.load(extracted)
                    self.menu.items[0].triggered.emit()
                    dialog = bootstrap._controller.dialog
                    Query.pending.pop(0).finish()
                    self.assertEqual(len(self.menu.items), 1)
                    self.assertEqual(dialog.audience.combo.index, -1)
                    dialog.audience.combo.setCurrentIndex(3)
                    self.assertEqual(dialog.audience.capture_settings().to_mapping(),
                                     {"audience": "certification"})
                    self.assertEqual(dialog.audience.status.text, "Audience: Certification")
                    self.hooks.profile_will_close[0]()


if __name__ == "__main__":
    unittest.main()
