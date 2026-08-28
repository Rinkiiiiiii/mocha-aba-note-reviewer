"""
HTML for the desktop app's two "chrome" screens: the home shell (pick a
file to review) and the settings screen (API key). Both are plain,
dependency-free HTML strings — no templating engine — matching the same
dark theme as core/report.py's report page so navigating between them (via
window.load_html) feels like one app instead of three different UIs.

The report screen itself is NOT built here — it's core.report.render_html,
reused as-is (see desktop/api.py), with a small nav bar injected via that
function's `top_bar_html` parameter.
"""

from __future__ import annotations

import html

# Shared with core/report.py's palette so all three screens feel like one app.
_BASE_STYLE = """
  :root {
    --bg: #14161c;
    --panel: #1b1e27;
    --border: #2b2f3a;
    --text: #e7e9ee;
    --muted: #9aa1b1;
    --accent: #7c9dff;
    --danger: #f2545b;
    --success: #3ddc97;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 2rem;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
  }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2rem;
  }
  .brand { font-size: 1.05rem; font-weight: 600; }
  .brand .sub { color: var(--muted); font-weight: 400; font-size: 0.85rem; display: block; }
  .icon-btn, .btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 8px;
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
    cursor: pointer;
    font-family: inherit;
  }
  .icon-btn:hover, .btn:hover { border-color: var(--accent); color: var(--accent); }
  .btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #10121a;
    font-weight: 600;
  }
  .btn.primary:hover { opacity: 0.9; color: #10121a; }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn:disabled:hover { border-color: var(--border); color: var(--text); }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem;
  }
  .banner {
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 1.5rem;
    font-size: 0.9rem;
  }
  .banner.warn { background: #2a2410; border: 1px solid #4a3f16; color: #f5c451; }
  .banner.error { background: #2a1416; border: 1px solid #4a1f22; color: var(--danger); }
  .banner.success { background: #123024; border: 1px solid #1f4a37; color: var(--success); }
  .muted { color: var(--muted); }
  .spinner {
    display: inline-block;
    width: 1rem; height: 1rem;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
    margin-right: 0.5rem;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
"""


def _top_nav(active_settings: bool = False) -> str:
    settings_action = (
        "" if active_settings else 'onclick="goSettings()"'
    )
    return f"""
    <div class="topbar">
      <div class="brand">Mocha ABA Note Reviewer<span class="sub">AI-assisted ABA note compliance review</span></div>
      <button class="icon-btn" id="settings-btn" {settings_action} {"disabled" if active_settings else ""}>&#9881; Settings</button>
    </div>
    """


def render_shell(status: dict, error: str | None = None) -> str:
    has_key = bool(status.get("has_api_key"))
    model = html.escape(status.get("model", ""))

    banner_html = ""
    if error:
        banner_html = f'<div class="banner error">{html.escape(error)}</div>'
    elif not has_key:
        banner_html = (
            '<div class="banner warn">No API key configured yet — '
            'add one in <button class="icon-btn" style="padding:0.1rem 0.5rem" '
            'onclick="goSettings()">Settings</button> before reviewing a note.</div>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Mocha ABA Note Reviewer</title>
<style>{_BASE_STYLE}
  .dropzone {{
    border: 2px dashed var(--border);
    border-radius: 16px;
    padding: 3rem 2rem;
    text-align: center;
    cursor: pointer;
  }}
  .dropzone:hover {{ border-color: var(--accent); }}
  .dropzone .big {{ font-size: 1.05rem; margin-bottom: 0.35rem; }}
  .footnote {{ margin-top: 1.5rem; font-size: 0.8rem; color: var(--muted); }}
</style>
</head>
<body>
  {_top_nav()}
  {banner_html}
  <div class="card">
    <div class="dropzone" id="dropzone" onclick="pickAndReview()">
      <div class="big" id="dropzone-label">&#128196; Select an ABA note (PDF or Word) to review</div>
      <div class="muted" id="dropzone-sub">Click to browse for a file</div>
    </div>
    <div class="footnote">
      Reviews are sent to OpenAI GPT-5.6 {model or "Terra"} after recognizable
      identifiers are redacted locally first. This is a risk-reduction
      measure, not a substitute for a signed BAA — see the README.
    </div>
  </div>
  <script>
    function goSettings() {{
      if (!window.pywebview) {{ return; }}
      window.pywebview.api.go_to_settings();
    }}

    function setBusy(message) {{
      var zone = document.getElementById("dropzone");
      var label = document.getElementById("dropzone-label");
      var sub = document.getElementById("dropzone-sub");
      zone.style.pointerEvents = "none";
      zone.style.opacity = "0.7";
      label.innerHTML = '<span class="spinner"></span>' + message;
      sub.textContent = "This can take up to a minute.";
    }}

    function pickAndReview() {{
      if (!window.pywebview) {{ return; }}
      window.pywebview.api.pick_file().then(function (picked) {{
        if (picked.error) {{
          window.pywebview.api.go_home_with_error(picked.error);
          return;
        }}
        if (!picked.path) {{
          return; // user cancelled the dialog
        }}
        setBusy("Reviewing " + picked.filename + "...");
        window.pywebview.api.review_note(picked.path).then(function (result) {{
          if (!result.ok) {{
            window.pywebview.api.go_home_with_error(result.error);
          }}
          // On success the Python side has already navigated the window to
          // the report screen — nothing further to do here.
        }});
      }});
    }}
  </script>
</body>
</html>
"""


def render_settings_page(status: dict, message: str | None = None, message_kind: str = "success") -> str:
    has_key = bool(status.get("has_api_key"))
    masked = html.escape(status.get("masked_key") or "")
    model = html.escape(status.get("model", ""))

    banner_html = ""
    if message:
        banner_html = f'<div class="banner {html.escape(message_kind)}">{html.escape(message)}</div>'

    current_key_html = (
        f'<p class="muted">Current key: <strong>{masked}</strong></p>' if has_key else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Settings — Mocha ABA Note Reviewer</title>
<style>{_BASE_STYLE}
  label {{ display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 0.35rem; }}
  input[type=password], input[type=text] {{
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    font-size: 0.9rem;
    font-family: inherit;
    margin-bottom: 0.75rem;
  }}
  input:focus {{ outline: none; border-color: var(--accent); }}
  .row {{ display: flex; gap: 0.6rem; align-items: center; margin-top: 0.5rem; }}
  .field-group {{ margin-bottom: 1.5rem; }}
</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">Settings<span class="sub">Mocha ABA Note Reviewer</span></div>
    <button class="icon-btn" onclick="goHome()">&#8592; Back</button>
  </div>
  {banner_html}
  <div class="card">
    <div class="field-group">
      <label for="api-key">OpenAI API key</label>
      {current_key_html}
      <input type="password" id="api-key" placeholder="sk-..." autocomplete="off" />
      <div class="row">
        <button class="btn primary" onclick="saveKey()">Save key</button>
        <button class="icon-btn" onclick="toggleShow()">Show</button>
        {'<button class="icon-btn" onclick="clearKey()">Remove key</button>' if has_key else ''}
      </div>
      <p class="muted" style="margin-top:0.75rem; font-size:0.8rem;">
        Stored only on this device (in your user config folder), used only to
        call OpenAI's API. Never sent anywhere else, never included in
        anything you export from this app.
      </p>
    </div>
    <div class="field-group">
      <label>Model</label>
      <p class="muted">GPT-5.6 {model or "Terra"} (fixed for now — see architecture-decisions.md for why).</p>
    </div>
    <p class="muted" style="font-size:0.8rem;">
      Notes are de-identified locally before being sent to this model. This
      is a risk-reduction measure, not a substitute for a signed BAA if
      you're working with real client PHI — confirm your compliance posture
      with whoever handles that for your practice.
    </p>
  </div>
  <script>
    function goHome() {{
      if (!window.pywebview) {{ return; }}
      window.pywebview.api.go_home();
    }}
    function toggleShow() {{
      var el = document.getElementById("api-key");
      el.type = el.type === "password" ? "text" : "password";
    }}
    function saveKey() {{
      if (!window.pywebview) {{ return; }}
      var value = document.getElementById("api-key").value;
      if (!value.trim()) {{ return; }}
      window.pywebview.api.save_api_key(value).then(function (res) {{
        if (!res.ok) {{
          window.pywebview.api.go_to_settings_with_message(res.error, "error");
          return;
        }}
        window.pywebview.api.go_to_settings_with_message("API key saved.", "success");
      }});
    }}
    function clearKey() {{
      if (!window.pywebview) {{ return; }}
      window.pywebview.api.clear_api_key().then(function () {{
        window.pywebview.api.go_to_settings_with_message("API key removed.", "success");
      }});
    }}
  </script>
</body>
</html>
"""
