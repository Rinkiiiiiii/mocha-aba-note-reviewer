"""
Tests DesktopAPI — the Python bridge exposed to the pywebview frontend as
`window.pywebview.api` — entirely against fakes/mocks, since this build
environment has no display or native webview backend to actually open a
window. `file_dialog`, `window_loader`, and `ai_client_factory` are the
three points DesktopAPI takes as injectable dependencies specifically to
make this possible.
"""

from desktop import config
from desktop.api import DesktopAPI
from core.ai_client import MockAIClient
from core.models import DetectedNote, FindingStatus, GuidelineFinding, NoteReview, Severity
from tests.helpers import make_pdf


def _use_tmp_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path / ".mocha_aba_reviewer")


class _EchoAIClient:
    """Echoes the note text it received into the review summary, so a test
    can confirm the report the desktop shell displays actually contains the
    real (rehydrated) note content — MockAIClient's fixed placeholder text
    wouldn't prove that either way."""

    def segment_document(self, text, codes):
        return {}

    def review_note(self, code, note_text, guideline_text):
        return NoteReview(
            note=DetectedNote(code=code, text=note_text),
            overall_status=FindingStatus.PARTIAL,
            summary=f"Reviewed: {note_text[:80]}",
            findings=[
                GuidelineFinding(
                    guideline_id="echo",
                    category="Echo",
                    status=FindingStatus.PARTIAL,
                    explanation="echo",
                    severity=Severity.LOW,
                )
            ],
        )


class _RecordingWindowLoader:
    def __init__(self):
        self.loaded = []

    def __call__(self, html_content):
        self.loaded.append(html_content)


def _make_note_pdf(tmp_path):
    path = tmp_path / "note.pdf"
    make_pdf(
        path,
        pages=[
            [
                "Client Name: Alex Rivera",
                "Billing Codes: 97153 (8)",
                "Session summary: Alex worked on requesting a break appropriately.",
            ]
        ],
    )
    return path


# --- status / settings -------------------------------------------------

def test_get_status_reflects_no_key_then_saved_key(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    api = DesktopAPI()

    assert api.get_status()["has_api_key"] is False

    api.save_api_key("sk-test-abc123")
    status = api.get_status()
    assert status["has_api_key"] is True
    assert status["masked_key"].startswith("sk-te")
    assert "abc123" not in status["masked_key"] or status["masked_key"].endswith("c123")


def test_save_api_key_rejects_blank_value(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    api = DesktopAPI()

    result = api.save_api_key("   ")
    assert result["ok"] is False
    assert api.get_status()["has_api_key"] is False


def test_clear_api_key_via_api(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    api = DesktopAPI()
    api.save_api_key("sk-test-abc123")
    result = api.clear_api_key()
    assert result["ok"] is True
    assert api.get_status()["has_api_key"] is False


# --- navigation ----------------------------------------------------------

def test_go_home_renders_warning_banner_when_no_key_configured(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    loader = _RecordingWindowLoader()
    api = DesktopAPI(window_loader=loader)

    api.go_home()

    assert len(loader.loaded) == 1
    assert "No API key configured" in loader.loaded[0]


def test_go_home_with_error_surfaces_message(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    loader = _RecordingWindowLoader()
    api = DesktopAPI(window_loader=loader)

    api.go_home_with_error("Something specific went wrong.")

    assert "Something specific went wrong." in loader.loaded[0]


def test_go_to_settings_with_message_shows_success_banner(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    loader = _RecordingWindowLoader()
    api = DesktopAPI(window_loader=loader)

    api.go_to_settings_with_message("API key saved.", "success")

    assert "API key saved." in loader.loaded[0]


# --- file picking ----------------------------------------------------------

def test_pick_file_returns_none_when_dialog_cancelled(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    api = DesktopAPI(file_dialog=lambda: None)

    result = api.pick_file()
    assert result == {"path": None}


def test_pick_file_rejects_unsupported_extension(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    fake_path = str(tmp_path / "note.txt")
    api = DesktopAPI(file_dialog=lambda: fake_path)

    result = api.pick_file()
    assert result["path"] is None
    assert "PDF or Word" in result["error"]


def test_pick_file_accepts_pdf_and_docx(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    fake_path = str(tmp_path / "note.pdf")
    api = DesktopAPI(file_dialog=lambda: fake_path)

    result = api.pick_file()
    assert result["path"] == fake_path
    assert result["filename"] == "note.pdf"


# --- review flow -----------------------------------------------------------

def test_review_note_without_api_key_fails_clearly_and_does_not_navigate(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    loader = _RecordingWindowLoader()
    api = DesktopAPI(window_loader=loader)
    pdf_path = _make_note_pdf(tmp_path)

    result = api.review_note(str(pdf_path))

    assert result["ok"] is False
    assert "Settings" in result["error"]
    assert loader.loaded == []


def test_review_note_success_navigates_to_report_with_new_review_bar(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    loader = _RecordingWindowLoader()
    api = DesktopAPI(
        window_loader=loader,
        ai_client_factory=lambda api_key, base_url, model: _EchoAIClient(),
    )
    api.save_api_key("sk-test-abc123")
    pdf_path = _make_note_pdf(tmp_path)

    result = api.review_note(str(pdf_path))

    assert result["ok"] is True
    assert len(loader.loaded) == 1
    assert "New review" in loader.loaded[0]
    assert "ABA Note Review" in loader.loaded[0]
    # The client name should have been restored locally (deidentify + rehydrate)
    # for display, even though _EchoAIClient only ever saw "[CLIENT_NAME]".
    assert "Alex Rivera" in loader.loaded[0]


def test_review_note_surfaces_extraction_failure_without_navigating(monkeypatch, tmp_path):
    # core.pipeline.review_document already catches per-note AI failures and
    # turns them into warnings rather than exceptions (see core/pipeline.py),
    # so the failure mode DesktopAPI's own try/except is guarding against is
    # further upstream — e.g. a bad/missing file. A .pdf path that doesn't
    # exist reliably raises inside core.extraction's PdfReader call, which
    # is NOT caught inside review_document, so it's the cleanest way to
    # exercise DesktopAPI's own error handling without reaching into
    # pipeline internals.
    _use_tmp_config_dir(monkeypatch, tmp_path)
    loader = _RecordingWindowLoader()
    api = DesktopAPI(
        window_loader=loader,
        ai_client_factory=lambda api_key, base_url, model: MockAIClient(),
    )
    api.save_api_key("sk-test-abc123")
    missing_path = str(tmp_path / "does-not-exist.pdf")

    result = api.review_note(missing_path)

    assert result["ok"] is False
    assert "Review failed" in result["error"]
    assert loader.loaded == []
