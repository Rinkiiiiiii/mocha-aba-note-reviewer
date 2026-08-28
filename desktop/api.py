"""
The Python-side bridge exposed to the pywebview frontend as
`window.pywebview.api`. Every public method here is called from JavaScript
(desktop/pages.py) and returns plain, JSON-serializable data — pywebview
marshals the call/return automatically.

`file_dialog` and `window_loader` are injected (defaulting to the real
pywebview calls) specifically so this class's actual logic — status
handling, error messages, wiring the redaction-enabled pipeline call — can
be unit tested without a real native window or display. This build
environment has neither, so that's not a hypothetical concern: see
tests/test_desktop_api.py for the test-side fakes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from core.pipeline import review_document
from core.report import render_html

from . import config
from .pages import render_settings_page, render_shell

_SUPPORTED_EXTENSIONS = (".pdf", ".docx")

_NEW_REVIEW_BAR = """
  <div style="display:flex; justify-content:flex-end; margin-bottom:1rem;">
    <button onclick="window.pywebview && window.pywebview.api.go_home()"
      style="background:transparent;border:1px solid #2b2f3a;color:#e7e9ee;
      border-radius:8px;padding:0.4rem 0.9rem;font-size:0.85rem;cursor:pointer;
      font-family:inherit;">&#8592; New review</button>
  </div>
"""


class DesktopAPI:
    def __init__(
        self,
        file_dialog: Optional[Callable[[], Optional[str]]] = None,
        window_loader: Optional[Callable[[str], None]] = None,
        ai_client_factory: Optional[Callable[[str, str, str], object]] = None,
    ):
        self._file_dialog = file_dialog or self._default_file_dialog
        self._window_loader = window_loader or self._default_window_loader
        self._ai_client_factory = ai_client_factory or self._default_ai_client_factory

    # --- status --------------------------------------------------------

    def get_status(self) -> dict:
        api_key = config.get_api_key()
        return {
            "has_api_key": bool(api_key),
            "masked_key": config.mask_api_key(api_key) if api_key else None,
            "model": config.get_model(),
        }

    # --- navigation (called from JS to swap screens) --------------------

    def go_home(self) -> dict:
        self._window_loader(render_shell(self.get_status()))
        return {"ok": True}

    def go_home_with_error(self, error: str) -> dict:
        self._window_loader(render_shell(self.get_status(), error=error))
        return {"ok": True}

    def go_to_settings(self) -> dict:
        self._window_loader(render_settings_page(self.get_status()))
        return {"ok": True}

    def go_to_settings_with_message(self, message: str, kind: str = "success") -> dict:
        self._window_loader(render_settings_page(self.get_status(), message=message, message_kind=kind))
        return {"ok": True}

    # --- settings actions ------------------------------------------------

    def save_api_key(self, raw_key: str) -> dict:
        try:
            config.save_api_key(raw_key)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def clear_api_key(self) -> dict:
        config.clear_api_key()
        return {"ok": True}

    # --- file selection / review ----------------------------------------

    def pick_file(self) -> dict:
        path = self._file_dialog()
        if not path:
            return {"path": None}
        if Path(path).suffix.lower() not in _SUPPORTED_EXTENSIONS:
            return {"path": None, "error": "Please choose a PDF or Word (.docx) file."}
        return {"path": path, "filename": Path(path).name}

    def review_note(self, path: str) -> dict:
        api_key = config.get_api_key()
        if not api_key:
            return {"ok": False, "error": "No API key saved yet — add one in Settings first."}

        client = self._ai_client_factory(api_key, config.get_base_url(), config.get_model())
        try:
            result = review_document(path, client, deidentify=True)
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI, never swallowed silently
            return {"ok": False, "error": f"Review failed: {exc}"}

        report_html = render_html(result, top_bar_html=_NEW_REVIEW_BAR)
        self._window_loader(report_html)
        return {"ok": True}

    # --- real (non-test) defaults ----------------------------------------

    @staticmethod
    def _default_ai_client_factory(api_key: str, base_url: str, model: str):
        from core.ai_client import HostedChatClient

        return HostedChatClient(api_key=api_key, base_url=base_url, model=model)

    @staticmethod
    def _default_file_dialog() -> Optional[str]:
        import webview

        window = webview.windows[0]
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("ABA notes (*.pdf;*.docx)", "All files (*.*)"),
        )
        return result[0] if result else None

    @staticmethod
    def _default_window_loader(html_content: str) -> None:
        import webview

        webview.windows[0].load_html(html_content)
