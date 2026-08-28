from core.models import NoteCode, SegmentationMethod
from core.segmentation import needs_ai_segmentation, segment_into_notes


def test_single_code_returns_whole_text_as_one_note():
    text = "This is a whole note about code 97153 with narrative content."
    notes = segment_into_notes(text, [NoteCode.RBT])
    assert len(notes) == 1
    assert notes[0].code == NoteCode.RBT
    assert notes[0].text == text
    assert notes[0].segmentation_method == SegmentationMethod.SINGLE_CODE
    assert not needs_ai_segmentation(notes)


def test_header_split_two_codes_with_clean_section_headers():
    # Mirrors the real Villa Lyan double-note sample structure.
    text = (
        "Header info: Billing Codes: 97155 (8), 97156 (4)\n\n"
        "Adaptive Behavior Service with Protocol Modification (CPT Code 97155):\n"
        "Summary: The BCBA conducted a supervision visit and modified the "
        "prompting procedure.\n\n"
        "Family Adaptive Behavior Treatment Guidance (CPT Code 97156):\n"
        "Summary: The BCBA conducted caregiver training on the same visit.\n"
    )
    notes = segment_into_notes(text, [NoteCode.SUPERVISION, NoteCode.PARENT_TRAINING])

    assert len(notes) == 2
    assert not needs_ai_segmentation(notes)

    by_code = {n.code: n for n in notes}
    assert by_code[NoteCode.SUPERVISION].segmentation_method == SegmentationMethod.HEADER_SPLIT
    assert "supervision visit" in by_code[NoteCode.SUPERVISION].text
    assert "caregiver training" not in by_code[NoteCode.SUPERVISION].text

    assert by_code[NoteCode.PARENT_TRAINING].segmentation_method == SegmentationMethod.HEADER_SPLIT
    assert "caregiver training" in by_code[NoteCode.PARENT_TRAINING].text
    assert "supervision visit" not in by_code[NoteCode.PARENT_TRAINING].text


def test_multiple_codes_without_headers_flagged_unresolved():
    # No "(CPT Code XXXXX)"-style headers at all -> can't split deterministically.
    text = (
        "Billing Codes: 97155 (8), 97156 (4)\n\n"
        "The BCBA conducted a combined visit covering both supervision and "
        "caregiver training with no clear section boundary in this narrative."
    )
    notes = segment_into_notes(text, [NoteCode.SUPERVISION, NoteCode.PARENT_TRAINING])

    assert len(notes) == 2
    assert needs_ai_segmentation(notes)
    for note in notes:
        assert note.segmentation_method == SegmentationMethod.UNRESOLVED
        assert note.confidence == 0.0
        assert note.text == text  # full text preserved for the AI to segment
        assert note.warnings


def test_partial_header_coverage_still_falls_back_to_unresolved():
    # Only one of the two codes has a section header -> not a clean split,
    # so both should be treated as needing AI segmentation rather than
    # silently guessing at the boundary for the unlabeled one.
    text = (
        "Some intro text mentioning 97155 and 97156.\n\n"
        "Family Adaptive Behavior Treatment Guidance (CPT Code 97156):\n"
        "Caregiver training content here.\n"
    )
    notes = segment_into_notes(text, [NoteCode.SUPERVISION, NoteCode.PARENT_TRAINING])
    assert needs_ai_segmentation(notes)
