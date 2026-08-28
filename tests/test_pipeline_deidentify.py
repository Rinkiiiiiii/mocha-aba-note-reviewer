"""
Verifies the pipeline's deidentify integration end-to-end: the AI backend
never sees the real identifier, but the final result the caller gets back
has real values restored.
"""

from core.models import DetectedNote, FindingStatus, GuidelineFinding, NoteReview, Severity
from core.pipeline import review_document
from tests.helpers import make_pdf

FAKE_GUIDELINE_DIR_CONTENT = "# 97153 guideline\n- Must describe targeted behaviors with data.\n"


class SpyAIClient:
    """Records exactly what text it was asked to review, and returns a
    review whose fields deliberately echo back a snippet of what it saw —
    so the test can check whether real PHI ever reached this "AI".
    """

    def __init__(self):
        self.received_note_texts = []

    def segment_document(self, text, codes):
        self.received_note_texts.append(text)
        return {}

    def review_note(self, code, note_text, guideline_text):
        self.received_note_texts.append(note_text)
        return NoteReview(
            note=DetectedNote(code=code, text=note_text),
            overall_status=FindingStatus.PARTIAL,
            summary=f"Reviewed note text: {note_text[:60]}",
            findings=[
                GuidelineFinding(
                    guideline_id="spy",
                    category="Spy",
                    status=FindingStatus.PARTIAL,
                    explanation="echo",
                    excerpt=note_text[:60],
                    suggested_fix=None,
                    severity=Severity.LOW,
                )
            ],
        )


def _write_guidelines(tmp_path):
    guidelines_dir = tmp_path / "guidelines"
    guidelines_dir.mkdir()
    (guidelines_dir / "97153.md").write_text(FAKE_GUIDELINE_DIR_CONTENT)
    return guidelines_dir


def test_ai_backend_never_receives_the_real_client_name(tmp_path):
    guidelines_dir = _write_guidelines(tmp_path)
    pdf_path = tmp_path / "note.pdf"
    make_pdf(
        pdf_path,
        pages=[
            [
                "Client Name: Jordan Alvarez",
                "Billing Codes: 97153 (20)",
                "Session summary: Jordan Alvarez had a productive session today.",
            ]
        ],
    )

    spy = SpyAIClient()
    result = review_document(pdf_path, spy, guidelines_dir=guidelines_dir, deidentify=True)

    # The spy "AI" must never have seen the real name anywhere.
    assert all("Jordan Alvarez" not in t for t in spy.received_note_texts)
    assert any("[CLIENT_NAME]" in t for t in spy.received_note_texts)

    # But the final, locally-returned result has the real name restored.
    assert result.reviews, "expected at least one review"
    assert "Jordan Alvarez" in result.reviews[0].summary
    assert "Jordan Alvarez" in result.reviews[0].findings[0].excerpt
    assert "Jordan Alvarez" in result.detected_notes[0].text
    assert any("Redacted" in w for w in result.warnings)


def test_deidentify_false_sends_real_text_through(tmp_path):
    guidelines_dir = _write_guidelines(tmp_path)
    pdf_path = tmp_path / "note.pdf"
    make_pdf(
        pdf_path,
        pages=[["Client Name: Jordan Alvarez", "Billing Codes: 97153 (20)"]],
    )

    spy = SpyAIClient()
    review_document(pdf_path, spy, guidelines_dir=guidelines_dir, deidentify=False)

    assert any("Jordan Alvarez" in t for t in spy.received_note_texts)
