from core.detection import detect_code_occurrences, detect_codes
from core.models import NoteCode


def test_detect_code_embedded_in_visits_field():
    # Mirrors the real "Care In Mind" 97156 sample: code sits inline in a
    # "Visits" field alongside provider name and duration, not in its own field.
    text = (
        "Visits: 8:15 am EDT to 10:15 am EDT (Jane Provider) 97156 | Duration: "
        "2:00 | Billable Units: 8 | Payer: FLORIDA MEDICAID (Professional) (M)"
    )
    assert detect_codes(text) == [NoteCode.PARENT_TRAINING]


def test_detect_code_embedded_in_differently_labeled_field():
    # Same vendor, different note type template, different field label
    # ("Logged Times for day" instead of "Visits") — confirms detection
    # doesn't depend on any particular field name.
    text = "Logged Times for day: 10:20 am EDT to 4:20 pm EDT (Some RBT) 97153\nDuration: 6:00"
    assert detect_codes(text) == [NoteCode.RBT]


def test_detect_code_in_dedicated_billing_field():
    text = "Billing Codes:\n97153 (20)"
    assert detect_codes(text) == [NoteCode.RBT]


def test_detect_two_codes_preserves_first_appearance_order():
    text = "Billing Codes: 97155 (8), 97156 (4)"
    assert detect_codes(text) == [NoteCode.SUPERVISION, NoteCode.PARENT_TRAINING]


def test_detect_deduplicates_repeated_codes():
    text = "97153 appears here, and again later: 97153 (20)"
    assert detect_codes(text) == [NoteCode.RBT]


def test_no_codes_found():
    assert detect_codes("Nothing billing-related in here at all.") == []


def test_does_not_false_positive_on_surrounding_digits():
    # 97153 embedded inside a longer number should NOT match.
    text = "Reference number 1971530000 should not match, but 97153 alone should."
    assert detect_codes(text) == [NoteCode.RBT]


def test_detect_code_occurrences_includes_context():
    text = "some prefix text 97155 some suffix text"
    occurrences = detect_code_occurrences(text, context_chars=10)
    assert len(occurrences) == 1
    assert occurrences[0]["code"] == "97155"
    assert "97155" in occurrences[0]["context"]
