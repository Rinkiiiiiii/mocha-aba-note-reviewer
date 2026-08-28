"""
Entry point for the actual desktop app: creates the native pywebview window
and starts its event loop.

Run with:  python -m desktop.main

This file is intentionally thin — almost everything worth testing lives in
desktop/api.py (unit tested against fakes) and desktop/pages.py. This file
itself needs a real display and a native webview backend (GTK/Qt on Linux,
WebView2 on Windows, WKWebView on macOS) to actually run, which is why it
isn't exercised by the test suite — there's no display in this build
environment. Run it on your own machine to see the app.
"""

from __future__ import annotations

import webview

from .api import DesktopAPI
from .pages import render_shell


def main() -> None:
    api = DesktopAPI()
    webview.create_window(
        "Mocha ABA Note Reviewer",
        html=render_shell(api.get_status()),
        js_api=api,
        width=980,
        height=760,
        min_size=(720, 560),
        background_color="#14161c",
    )
    webview.start()


if __name__ == "__main__":
    main()
