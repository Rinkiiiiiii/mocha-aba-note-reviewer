from core.models import (
    DetectedNote,
    DocumentReviewResult,
    FindingStatus,
    GuidelineFinding,
    NoteCode,
    NoteReview,
    Severity,
)
from core.report import render_html, render_markdown


def _sample_result() -> DocumentReviewResult:
    note = DetectedNote(code=NoteCode.RBT, text="Some note text.")
    finding = GuidelineFinding(
        guideline_id="target_behaviors",
        category="Targeted Behaviors",
        status=FindingStatus.NOT_MET,
        explanation="No objective data was recorded for the targeted behavior.",
        excerpt="The client had a fair day.",
        suggested_fix="Record frequency/duration data for each targeted behavior.",
        severity=Severity.HIGH,
    )
    review = NoteReview(
        note=note,
        overall_status=FindingStatus.NOT_MET,
        summary="This note is missing required objective behavior data.",
        findings=[finding],
    )
    return DocumentReviewResult(source_filename="test_note.pdf", detected_notes=[note], reviews=[review], warnings=["Removed trailing DocuSign audit-trail pages before review."])


def test_render_markdown_contains_key_content():
    md = render_markdown(_sample_result())
    assert "test_note.pdf" in md
    assert "RBT Note" in md
    assert "Targeted Behaviors" in md
    assert "fair day" in md
    assert "Record frequency/duration data" in md


def test_render_markdown_handles_no_reviews():
    empty = DocumentReviewResult(source_filename="empty.pdf")
    md = render_markdown(empty)
    assert "No reviewed notes" in md


def test_render_html_is_self_contained_and_escapes_content():
    result = _sample_result()
    result.reviews[0].summary = "<script>alert(1)</script>"
    out = render_html(result)

    assert "<html" in out
    assert "test_note.pdf" in out
    # No external asset references — must be fully self-contained.
    assert "http://" not in out
    assert "https://" not in out
    # User/AI-supplied content must be escaped, not injected raw.
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out
