"""
Turning a DocumentReviewResult into human-facing output.

Two pure functions, no UI framework dependency:

  * render_markdown — clean, copy-pasteable text. This is what the "copy for
    AI" button in the eventual UI should put on the clipboard, since the
    whole point of the report (per the original project brief) is making it
    easy to hand to a *different* AI to help fix the note.
  * render_html — a self-contained, dark-themed HTML document for display.
    Kept dependency-free (inline <style>/<script>, no external assets) so it
    can be dropped into a pywebview window, a browser, or anywhere else
    without modification.
"""

from __future__ import annotations

import html

from .models import DocumentReviewResult, FindingStatus, NoteReview, Severity

_STATUS_LABEL = {
    FindingStatus.MET: "Met",
    FindingStatus.PARTIAL: "Partial",
    FindingStatus.NOT_MET: "Not Met",
}

_STATUS_COLOR = {
    FindingStatus.MET: "#3ddc97",
    FindingStatus.PARTIAL: "#f5c451",
    FindingStatus.NOT_MET: "#f2545b",
}

_SEVERITY_LABEL = {
    Severity.LOW: "Low",
    Severity.MEDIUM: "Medium",
    Severity.HIGH: "High",
}


# --- Markdown ----------------------------------------------------------

def render_markdown(result: DocumentReviewResult) -> str:
    lines: list[str] = [f"# ABA Note Review — {result.source_filename}", ""]

    if result.warnings:
        lines.append("> **Warnings**")
        for w in result.warnings:
            lines.append(f"> - {w}")
        lines.append("")

    if not result.reviews:
        lines.append("_No reviewed notes to show._")
        return "\n".join(lines)

    for review in result.reviews:
        lines.append(f"## {review.note.label}")
        lines.append(f"**Overall status:** {_STATUS_LABEL[review.overall_status]}")
        lines.append("")
        lines.append(review.summary)
        lines.append("")
        for finding in review.findings:
            lines.append(f"### {finding.category} — {_STATUS_LABEL[finding.status]} ({_SEVERITY_LABEL[finding.severity]} severity)")
            lines.append(finding.explanation)
            if finding.excerpt:
                lines.append("")
                lines.append(f"> {finding.excerpt}")
            if finding.suggested_fix:
                lines.append("")
                lines.append(f"**Suggested fix:** {finding.suggested_fix}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


# --- HTML ----------------------------------------------------------------

def _finding_html(finding) -> str:
    color = _STATUS_COLOR[finding.status]
    excerpt_html = (
        f'<blockquote class="excerpt">{html.escape(finding.excerpt)}</blockquote>'
        if finding.excerpt
        else ""
    )
    fix_html = (
        f'<p class="fix"><strong>Suggested fix:</strong> {html.escape(finding.suggested_fix)}</p>'
        if finding.suggested_fix
        else ""
    )
    return f"""
    <div class="finding" style="border-left-color:{color}">
      <div class="finding-head">
        <span class="finding-category">{html.escape(finding.category)}</span>
        <span class="badge" style="background:{color}22;color:{color}">{_STATUS_LABEL[finding.status]}</span>
        <span class="severity severity-{finding.severity.value}">{_SEVERITY_LABEL[finding.severity]} severity</span>
      </div>
      <p class="finding-explanation">{html.escape(finding.explanation)}</p>
      {excerpt_html}
      {fix_html}
    </div>
    """


def _review_section_html(review: NoteReview, index: int) -> str:
    color = _STATUS_COLOR[review.overall_status]
    findings_html = "".join(_finding_html(f) for f in review.findings) or "<p class='muted'>No findings returned.</p>"
    warnings_html = ""
    if review.note.warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in review.note.warnings)
        warnings_html = f'<ul class="note-warnings">{items}</ul>'

    return f"""
    <section class="note-review">
      <header class="note-review-head">
        <h2>{html.escape(review.note.label)}</h2>
        <span class="badge overall" style="background:{color}22;color:{color}">{_STATUS_LABEL[review.overall_status]}</span>
        <button class="copy-btn" data-note-index="{index}" type="button">Copy as Markdown</button>
      </header>
      <p class="summary">{html.escape(review.summary)}</p>
      {warnings_html}
      <div class="findings">{findings_html}</div>
    </section>
    """


_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>ABA Note Review — {source_filename}</title>
<style>
  :root {{
    --bg: #14161c;
    --panel: #1b1e27;
    --border: #2b2f3a;
    --text: #e7e9ee;
    --muted: #9aa1b1;
    --accent: #7c9dff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 2rem;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
  }}
  h1 {{ font-size: 1.4rem; margin: 0 0 0.25rem; }}
  .filename {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .doc-warnings {{
    background: #2a2410;
    border: 1px solid #4a3f16;
    color: #f5c451;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 1.5rem;
    font-size: 0.9rem;
  }}
  .doc-warnings ul {{ margin: 0.25rem 0 0; padding-left: 1.25rem; }}
  .note-review {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .note-review-head {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }}
  .note-review-head h2 {{ font-size: 1.1rem; margin: 0; flex: 1 1 auto; }}
  .badge {{
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    white-space: nowrap;
  }}
  .severity {{ font-size: 0.75rem; color: var(--muted); }}
  .copy-btn {{
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 8px;
    padding: 0.35rem 0.75rem;
    font-size: 0.8rem;
    cursor: pointer;
  }}
  .copy-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .copy-btn.copied {{ border-color: #3ddc97; color: #3ddc97; }}
  .summary {{ color: var(--muted); margin: 0.75rem 0 1rem; }}
  .note-warnings {{ color: #f5c451; font-size: 0.85rem; }}
  .finding {{
    border-left: 3px solid var(--border);
    padding: 0.6rem 0 0.6rem 1rem;
    margin-bottom: 0.9rem;
  }}
  .finding-head {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.35rem; flex-wrap: wrap; }}
  .finding-category {{ font-weight: 600; }}
  .finding-explanation {{ margin: 0.25rem 0; }}
  .excerpt {{
    margin: 0.5rem 0;
    padding: 0.5rem 0.75rem;
    background: #00000030;
    border-left: 2px solid var(--border);
    color: var(--muted);
    font-style: italic;
  }}
  .fix {{ margin: 0.25rem 0 0; }}
  .muted {{ color: var(--muted); }}
</style>
</head>
<body>
  {top_bar_html}
  <h1>ABA Note Review</h1>
  <div class="filename">{source_filename}</div>
  {doc_warnings_html}
  {sections_html}

  <script id="review-markdown-payload" type="application/json">{markdown_json}</script>
  <script>
    (function () {{
      var payload = JSON.parse(document.getElementById("review-markdown-payload").textContent);
      document.querySelectorAll(".copy-btn").forEach(function (btn) {{
        btn.addEventListener("click", function () {{
          var idx = btn.getAttribute("data-note-index");
          var text = payload[idx] || "";
          navigator.clipboard.writeText(text).then(function () {{
            btn.classList.add("copied");
            var original = btn.textContent;
            btn.textContent = "Copied!";
            setTimeout(function () {{
              btn.classList.remove("copied");
              btn.textContent = original;
            }}, 1500);
          }});
        }});
      }});
    }})();
  </script>
</body>
</html>
"""


def render_html(result: DocumentReviewResult, top_bar_html: str = "") -> str:
    """Render the full self-contained report page.

    `top_bar_html` is an optional raw HTML snippet inserted right after
    <body>, before the report content. It exists so a host UI (e.g. the
    pywebview desktop shell) can inject its own nav bar (a "New Review"
    button, etc.) without this module needing to know anything about that
    host — plain string content in, plain string HTML out either way. Left
    empty by default so standalone use (CLI scripts, tests) is unaffected.
    """
    import json as _json

    doc_warnings_html = ""
    if result.warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in result.warnings)
        doc_warnings_html = f'<div class="doc-warnings"><strong>Warnings</strong><ul>{items}</ul></div>'

    if not result.reviews:
        sections_html = '<p class="muted">No reviewed notes to show.</p>'
        markdown_by_index = {}
    else:
        sections_html = "".join(
            _review_section_html(review, i) for i, review in enumerate(result.reviews)
        )
        # Per-note markdown (for the individual "Copy as Markdown" buttons):
        # reuse render_markdown by building a single-review sub-result.
        markdown_by_index = {
            str(i): render_markdown(
                DocumentReviewResult(source_filename=result.source_filename, reviews=[review])
            )
            for i, review in enumerate(result.reviews)
        }

    # Escaping "<" as its unicode escape neutralizes any "</script>" sequence
    # that might appear inside AI-generated or note-derived text (excerpts,
    # summaries, suggested fixes). Without this, such a sequence would
    # prematurely close the enclosing <script type="application/json"> tag
    # at the HTML-parser level — regardless of JS/JSON string quoting — and
    # everything after it would be parsed as raw page markup instead of JSON.
    safe_markdown_json = _json.dumps(markdown_by_index).replace("<", "\\u003c")

    return _PAGE_TEMPLATE.format(
        source_filename=html.escape(result.source_filename),
        top_bar_html=top_bar_html,
        doc_warnings_html=doc_warnings_html,
        sections_html=sections_html,
        markdown_json=safe_markdown_json,
    )
