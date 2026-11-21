from aqt.operations import QueryOp
from aqt.qt import QDialog, QLabel, QPushButton, Qt, QVBoxLayout, qconnect

from ..models.auth import AddonError, OAuthConfig
from ..services.oauth import OAuthSession
from ..services.privacy import event


class SignInDialog(QDialog):
    def __init__(self, mw, config: OAuthConfig, profile: str):
        super().__init__(mw)
        self.setWindowTitle("Anki AI Deck Generator - Sign in")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.active = True
        self.busy = False
        self.session = OAuthSession(config, profile)
        layout = QVBoxLayout(self)
        description = QLabel(
            "Sign in using your system browser. Refresh credentials are saved only "
            "in the protected OS store; access tokens stay in memory.\n\n"
            "This foundation does not upload documents or modify your collection. "
            "Cloud processing, consent and review belong to subsequent releases."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status = QLabel("Not signed in during this session.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.signin = QPushButton("Sign in with browser")
        self.resume = QPushButton("Use saved sign-in")
        self.signout = QPushButton("Sign out locally")
        self.cancel_button = QPushButton("Cancel / Close")
        for button in (self.signin, self.resume, self.signout, self.cancel_button):
            layout.addWidget(button)
        qconnect(self.signin.clicked, lambda: self.run(self.session.sign_in, "signed_in"))
        qconnect(self.resume.clicked, lambda: self.run(self._resume, "signed_in"))
        qconnect(self.signout.clicked, lambda: self.run(self.session.sign_out, "signed_out_ok"))
        qconnect(self.cancel_button.clicked, self.reject)

    def _resume(self) -> None:
        self.session.access_token()

    def run(self, operation, success_code: str) -> None:
        if self.busy:
            return
        self.busy = True
        self._buttons(False)
        self.status.setText("Working... Complete sign-in in your browser, or cancel.")

        def success(result):
            if not self.active:
                return
            self.busy = False
            self._buttons(True)
            event(success_code)
            self.status.setText(
                "Signed in. No documents have been uploaded."
                if success_code == "signed_in"
                else "Signed out locally. Browser/identity-provider sessions are unchanged."
            )

        def failure(error):
            safe = error if isinstance(error, AddonError) else AddonError("internal")
            event(safe.code)
            if not self.active:
                return
            self.busy = False
            self._buttons(True)
            self.status.setText(str(safe))

        try:
            (
                QueryOp(parent=self, op=lambda _collection: operation(), success=success)
                .without_collection()
                .failure(failure)
                .run_in_background()
            )
        except Exception as error:
            failure(error)

    def _buttons(self, enabled: bool):
        for button in (self.signin, self.resume, self.signout):
            button.setEnabled(enabled)

    def reject(self) -> None:
        self.active = False
        self.session.close()
        super().reject()

    def closeEvent(self, event):
        self.active = False
        self.session.close()
        super().closeEvent(event)
