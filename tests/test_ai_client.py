import pytest

from core.ai_client import AIBackendError, MockAIClient, _extract_json_object
from core.models import NoteCode


def test_extract_json_object_plain():
    raw = '{"a": 1, "b": "two"}'
    assert _extract_json_object(raw) == {"a": 1, "b": "two"}


def test_extract_json_object_strips_markdown_fences():
    raw = '```json\n{"a": 1}\n```'
    assert _extract_json_object(raw) == {"a": 1}


def test_extract_json_object_finds_first_balanced_object_amid_commentary():
    raw = 'Sure, here is the JSON:\n{"a": {"nested": 1}}\nHope that helps!'
    assert _extract_json_object(raw) == {"a": {"nested": 1}}


def test_extract_json_object_raises_on_garbage():
    with pytest.raises(AIBackendError):
        _extract_json_object("no json here at all")


def test_mock_client_segment_document_covers_all_codes():
    client = MockAIClient()
    text = "a" * 100
    result = client.segment_document(text, [NoteCode.SUPERVISION, NoteCode.PARENT_TRAINING])
    assert set(result.keys()) == {NoteCode.SUPERVISION, NoteCode.PARENT_TRAINING}
    assert "".join(result.values()).replace(" ", "") != ""


def test_mock_client_review_note_returns_placeholder_finding():
    client = MockAIClient()
    review = client.review_note(NoteCode.RBT, "some note text", "some guideline text")
    assert review.findings
    assert review.findings[0].guideline_id == "mock"
