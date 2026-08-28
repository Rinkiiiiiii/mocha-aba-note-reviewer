from core.ai_client import MockAIClient
from core.models import FindingStatus, SegmentationMethod
from core.pipeline import review_document
from tests.helpers import make_pdf

FAKE_GUIDELINES = {
    "97153.md": "# 97153 guideline\n- Must describe targeted behaviors with data.\n",
    "97155.md": "# 97155 guideline\n- Must describe protocol modifications with rationale.\n",
    "97156.md": "# 97156 guideline\n- Must describe caregiver training content and response.\n",
}


def _write_fake_guidelines(tmp_path):
    guidelines_dir = tmp_path / "guidelines"
    guidelines_dir.mkdir()
    for filename, content in FAKE_GUIDELINES.items():
        (guidelines_dir / filename).write_text(content)
    return guidelines_dir


def test_review_document_single_code(tmp_path):
    guidelines_dir = _write_fake_guidelines(tmp_path)
    pdf_path = tmp_path / "note.pdf"
    make_pdf(pdf_path, pages=[["Billing Codes: 97153 (20)", "Summary: services rendered at home."]])

    result = review_document(pdf_path, MockAIClient(), guidelines_dir=guidelines_dir)

    assert result.note_count == 1
    assert result.detected_notes[0].segmentation_method == SegmentationMethod.SINGLE_CODE
    assert len(result.reviews) == 1
    assert result.reviews[0].overall_status == FindingStatus.PARTIAL  # MockAIClient's fixed response


def test_review_document_two_codes_with_headers(tmp_path):
    guidelines_dir = _write_fake_guidelines(tmp_path)
    pdf_path = tmp_path / "note.pdf"
    make_pdf(
        pdf_path,
        pages=[
            [
                "Billing Codes: 97155 (8), 97156 (4)",
                "Adaptive Behavior Service with Protocol Modification (CPT Code 97155):",
                "Summary: supervision content here.",
                "Family Adaptive Behavior Treatment Guidance (CPT Code 97156):",
                "Summary: caregiver training content here.",
            ]
        ],
    )

    result = review_document(pdf_path, MockAIClient(), guidelines_dir=guidelines_dir)

    assert result.note_count == 2
    methods = {n.segmentation_method for n in result.detected_notes}
    assert methods == {SegmentationMethod.HEADER_SPLIT}
    assert len(result.reviews) == 2


def test_review_document_two_codes_without_headers_uses_ai_segmentation(tmp_path):
    guidelines_dir = _write_fake_guidelines(tmp_path)
    pdf_path = tmp_path / "note.pdf"
    make_pdf(
        pdf_path,
        pages=[
            [
                "Billing Codes: 97155 (8), 97156 (4)",
                "One continuous narrative covering both supervision and caregiver",
                "training with no clear section boundary at all in this text.",
            ]
        ],
    )

    result = review_document(pdf_path, MockAIClient(), guidelines_dir=guidelines_dir)

    assert result.note_count == 2
    methods = {n.segmentation_method for n in result.detected_notes}
    assert methods == {SegmentationMethod.AI_SPLIT}
    assert len(result.reviews) == 2


def test_review_document_no_code_found(tmp_path):
    guidelines_dir = _write_fake_guidelines(tmp_path)
    pdf_path = tmp_path / "note.pdf"
    make_pdf(pdf_path, pages=[["Nothing billing related in this document at all."]])

    result = review_document(pdf_path, MockAIClient(), guidelines_dir=guidelines_dir)

    assert result.note_count == 0
    assert len(result.reviews) == 0
    assert any("No recognized billing code" in w for w in result.warnings)


def test_review_document_skips_review_for_unconfigured_placeholder_guideline(tmp_path):
    # A guidelines dir where the file is still the un-filled-in placeholder
    # (as core/guidelines.py ships by default until real criteria are added)
    # should fail loudly as a warning rather than silently reviewing against
    # an empty ruleset.
    guidelines_dir = tmp_path / "guidelines"
    guidelines_dir.mkdir()
    (guidelines_dir / "97153.md").write_text("<!-- PLACEHOLDER: not filled in yet -->")

    pdf_path = tmp_path / "note.pdf"
    make_pdf(pdf_path, pages=[["Billing Codes: 97153 (20)"]])

    result = review_document(pdf_path, MockAIClient(), guidelines_dir=guidelines_dir)

    assert result.note_count == 1
    assert len(result.reviews) == 0
    assert any("Skipped review of 97153" in w for w in result.warnings)


def test_review_document_uses_real_repo_guidelines_by_default(tmp_path):
    # Now that guidelines/*.md have been filled in with real CASP-derived
    # content, the default (no guidelines_dir passed) path should succeed
    # end-to-end for all three codes.
    pdf_path = tmp_path / "note.pdf"
    make_pdf(pdf_path, pages=[["Billing Codes: 97153 (20)"]])

    result = review_document(pdf_path, MockAIClient())

    assert result.note_count == 1
    assert len(result.reviews) == 1
    assert not any("Skipped review" in w for w in result.warnings)
