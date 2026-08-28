"""
Desktop UI package (pywebview). Everything in `core/` is UI-agnostic; this
package is the thin wrapper that makes it a native-feeling desktop app.

Layout:
  config.py   Local, on-device storage for the OpenAI API key + model choice.
  api.py      DesktopAPI — the Python bridge exposed to the JS frontend as
              `window.pywebview.api`. Dependency-injectable so it's unit
              testable without a real native window.
  pages.py    Builds the HTML strings for the shell/settings screens. The
              report screen itself reuses core.report.render_html.
  main.py     Actual entry point: creates the pywebview window and starts
              the native event loop. Not unit tested — requires a real
              display/GUI backend, which this build environment doesn't
              have. Run `python -m desktop.main` on your own machine.
"""
