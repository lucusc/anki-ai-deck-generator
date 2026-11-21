from threading import Event

from aqt.operations import CollectionOp, QueryOp
from aqt.qt import QComboBox, QLabel, QLineEdit, QPushButton, Qt, QVBoxLayout, QWidget, qconnect

from ..models.auth import AddonError
from ..models.deck import DeckError, DeckIdentity, DeckSelection, validate_deck_name
from ..services.decks import create_deck, list_decks
from ..services.privacy import LOGGER, event


class DeckSelector(QWidget):
    def __init__(self, parent, selection: DeckSelection, on_busy):
        super().__init__(parent)
        self.selection = selection
        self.on_busy = on_busy
        self.closed = Event()
        self.busy = False
        self.available = True
        self.decks = ()
        layout = QVBoxLayout(self)
        label = QLabel("Destination deck (normal decks only; filtered decks are not import targets)")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.combo = QComboBox()
        self.combo.setPlaceholderText("Select a destination deck")
        self.refresh_button = QPushButton("Refresh decks / check selection")
        self.name = QLineEdit()
        self.name.setPlaceholderText("New deck name, e.g. Synthetic::Biology")
        self.create_button = QPushButton("Create new deck")
        self.status = QLabel("Select a destination deck before continuing.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        for widget in (self.combo, self.refresh_button, self.name, self.create_button, self.status):
            layout.addWidget(widget)
        qconnect(self.combo.currentIndexChanged, self.select)
        qconnect(self.refresh_button.clicked, self.refresh)
        qconnect(self.create_button.clicked, self.create)

    def set_available(self, available: bool):
        self.available = available
        for widget in (self.combo, self.refresh_button, self.name, self.create_button):
            widget.setEnabled(available and not self.busy and not self.closed.is_set())

    def _begin(self) -> bool:
        if self.busy or not self.available or self.closed.is_set():
            return False
        self.busy = True
        self.set_available(self.available)
        self.on_busy(True)
        return True

    def _finish(self):
        self.busy = False
        self.set_available(self.available)
        self.on_busy(False)

    def _guard(self):
        if self.closed.is_set():
            raise DeckError("closed")

    def _failure(self, error):
        if isinstance(error, DeckError):
            LOGGER.info("anki_ai_deck_generator deck_event=%s", error.code)
            safe = error
        else:
            safe = AddonError("internal")
            event(safe.code)
        if self.closed.is_set():
            return
        self._finish()
        self.status.setText(str(safe))

    def select(self, index: int):
        if self.closed.is_set() or self.busy or not self.available or index < 0:
            return
        self.selection.target = self.decks[index]
        self.status.setText("Destination selected. Refresh to check changes before continuing.")

    def _populate(self, decks):
        self.decks = decks
        previous = self.selection.target
        self.combo.blockSignals(True)
        self.combo.clear()
        selected_index = -1
        for index, deck in enumerate(decks):
            self.combo.addItem(deck.name, deck.deck_id)
            if previous is not None and deck.deck_id == previous.deck_id:
                selected_index = index
                self.selection.target = deck
        self.combo.setCurrentIndex(selected_index)
        self.combo.blockSignals(False)
        if previous is None:
            self.status.setText(str(DeckError("unselected")))
        elif selected_index < 0:
            self.status.setText(str(DeckError("missing")))
        elif self.selection.target.name != previous.name:
            self.status.setText("The selected deck was renamed. The same deck ID is still selected.")
        else:
            self.status.setText("Destination deck checked. The same deck ID is still selected.")

    def refresh(self):
        if not self._begin():
            return

        def read(collection):
            self._guard()
            return list_decks(collection)

        def success(decks):
            if self.closed.is_set():
                return
            self._populate(decks)
            self._finish()

        try:
            QueryOp(parent=self, op=read, success=success).failure(
                self._failure
            ).run_in_background()
        except Exception as error:
            self._failure(error)

    def create(self):
        if self.busy or not self.available or self.closed.is_set():
            return
        try:
            name = validate_deck_name(self.name.text())
        except DeckError as error:
            self._failure(error)
            return
        if not self._begin():
            return

        def write(collection):
            self._guard()
            return create_deck(collection, name)

        def success(result):
            if self.closed.is_set():
                return
            self.selection.target = DeckIdentity(int(result.id), name)
            self.name.clear()
            self._finish()
            self.refresh()

        try:
            CollectionOp(self, write).success(success).failure(
                self._failure
            ).run_in_background()
        except Exception as error:
            self._failure(error)

    def close_selector(self):
        self.closed.set()
