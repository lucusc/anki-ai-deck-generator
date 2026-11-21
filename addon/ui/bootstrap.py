from ..models.auth import AddonError, OAuthConfig
from ..services.privacy import event

TARGET_VERSIONS = {"25.09", "26.09.4"}
ACTION_NAME = "anki_ai_deck_generator"
_controller = None


def install(package_name: str) -> None:
    global _controller
    try:
        from anki.buildinfo import version
        from aqt import gui_hooks, mw
        from aqt.qt import QAction, qconnect
        from aqt.utils import showWarning

        if mw is None:
            raise AddonError("startup")
        if any(action.objectName() == ACTION_NAME for action in mw.form.menuTools.actions()):
            return
        action = QAction("Anki AI Deck Generator...", mw)
        action.setObjectName(ACTION_NAME)
        mw.form.menuTools.addAction(action)

        class Controller:
            dialog = None

            def open(self):
                try:
                    if version not in TARGET_VERSIONS:
                        raise AddonError("unsupported")
                    if self.dialog is not None and self.dialog.active:
                        self.dialog.show()
                        self.dialog.raise_()
                        self.dialog.activateWindow()
                        return
                    config = OAuthConfig.from_mapping(mw.addonManager.getConfig(package_name))
                    from .signin import SignInDialog

                    self.dialog = SignInDialog(mw, config, mw.pm.name)
                    self.dialog.show()
                except Exception as error:
                    safe = error if isinstance(error, AddonError) else AddonError("internal")
                    event(safe.code)
                    showWarning(str(safe), parent=mw)

            def close(self):
                if self.dialog is not None:
                    if self.dialog.active:
                        self.dialog.reject()
                    self.dialog = None

        _controller = Controller()
        qconnect(action.triggered, lambda checked=False: _controller.open())
        gui_hooks.profile_will_close.append(_controller.close)
        event("loaded")
        if version not in TARGET_VERSIONS:
            event("unsupported")
            gui_hooks.main_window_did_init.append(
                lambda: showWarning(str(AddonError("unsupported")), parent=mw)
            )
    except Exception as error:
        safe = error if isinstance(error, AddonError) else AddonError("startup")
        event(safe.code)
        # Startup is a trust boundary: never expose raw tracebacks or config.
        try:
            from aqt.utils import showWarning

            showWarning(str(safe))
        except (ImportError, AttributeError):
            event("startup")
