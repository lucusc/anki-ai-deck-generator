from aqt.qt import QComboBox, QLabel, Qt, QVBoxLayout, QWidget, qconnect

from ..models.audience import Audience, AudienceError, AudienceSelection, AudienceSettings


class AudienceSelector(QWidget):
    def __init__(self, parent, selection: AudienceSelection):
        super().__init__(parent)
        self.selection = selection
        self.available = True
        self.closed = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Audience (required; no default is selected)"))
        self.combo = QComboBox()
        self.combo.setPlaceholderText("Select an audience")
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.combo.blockSignals(True)
        selected_index = -1
        for index, audience in enumerate(Audience):
            self.combo.addItem(audience.label, audience.value)
            if selection.settings is not None and selection.settings.audience is audience:
                selected_index = index
        self.combo.setCurrentIndex(selected_index)
        self.combo.blockSignals(False)
        self.status.setText(
            selection.settings.review_label
            if selection.settings is not None
            else str(AudienceError("missing"))
        )
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        qconnect(self.combo.currentIndexChanged, self.select)

    def select(self, index: int):
        if self.closed or not self.available:
            return
        if index == -1:
            self.selection.settings = None
            self.status.setText(str(AudienceError("missing")))
            return
        try:
            self.selection.choose(self.combo.itemData(index))
        except AudienceError as error:
            self.status.setText(str(error))
            return
        self.status.setText(self.selection.capture().review_label)

    def capture_settings(self) -> AudienceSettings:
        if self.closed:
            raise AudienceError("closed")
        return self.selection.capture()

    def set_available(self, available: bool):
        self.available = available
        self.combo.setEnabled(available and not self.closed)

    def close_selector(self):
        self.closed = True
        self.set_available(False)
