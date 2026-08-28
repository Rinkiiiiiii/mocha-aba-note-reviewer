"""
Top-level orchestration: file in, structured review(s) out.

This is the one function a UI layer (pywebview today, potentially something
else later) actually needs to call. It has no idea what's calling it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .ai_client import AIReviewClient
from .deidentify import redact, rehydrate_result
from .detection import detect_codes
from .extraction import extract_document_text
from .guidelines import load_guideline
from .models import DocumentReviewResult, SegmentationMethod
from .segmentation import needs_ai_segmentation, segment_into_notes


def review_document(
    path: Union[str, Path],
    ai_client: AIReviewClient,
    *,
    guidelines_dir: Optional[Path] = None,
    deidentify: bool = True,
) -> DocumentReviewResult:
    """Run the full pipeline on one uploaded file.

    Steps:
      1. Extract plain text (PDF/DOCX), stripping DocuSign boilerplate.
      2. If `deidentify` (default True): redact recognizable identifiers
         (see core.deidentify) so the AI backend never receives them —
         everything downstream (detection, segmentation, AI calls) operates
         on the redacted text.
      3. Detect which of the three billing codes are present, anywhere.
      4. Segment the text into one note per detected code (deterministic
         header-split when possible, AI-assisted when not).
      5. Load each note's guideline text and ask the AI client to review it.
      6. If `deidentify`: reverse the substitution in the returned notes/
         reviews so the LOCAL result still shows real values — only the AI
         backend was kept from seeing them.

    `deidentify=True` is a technical risk-reduction measure, not a
    substitute for confirming your actual compliance posture — see the
    module docstring in core/deidentify.py before relying on it in place of
    a BAA.

    Returns a DocumentReviewResult even when nothing was detected or an
    AI call fails for one note — check `.warnings` and inspect
    `.reviews` vs `.detected_notes` rather than assuming success.
    """
    path = Path(path)
    result = DocumentReviewResult(source_filename=path.name)

    extracted = extract_document_text(path)
    result.warnings.extend(extracted.warnings)
    if extracted.docusign_stripped:
        result.warnings.append("Removed trailing DocuSign audit-trail pages before review.")

    if deidentify:
        working_text, reverse_map = redact(extracted.full_text)
        if reverse_map:
            result.warnings.append(
                f"Redacted {len(reverse_map)} recognized identifier(s) before sending "
                "this note's text to the AI backend."
            )
    else:
        working_text, reverse_map = extracted.full_text, {}

    codes = detect_codes(working_text)
    if not codes:
        result.warnings.append(
            "No recognized billing code (97153/97155/97156) was found anywhere "
            "in this document's extracted text."
        )
        return result

    notes = segment_into_notes(working_text, codes)

    if needs_ai_segmentation(notes):
        try:
            segmented = ai_client.segment_document(working_text, codes)
        except Exception as exc:
            result.warnings.append(
                f"AI-assisted segmentation failed ({exc}); falling back to "
                "reviewing the full document text against each detected code's "
                "guideline. Findings may be less precise for multi-note documents."
            )
            segmented = {}

        rebuilt = []
        for note in notes:
            if note.code in segmented and segmented[note.code].strip():
                rebuilt.append(
                    note.__class__(
                        code=note.code,
                        text=segmented[note.code].strip(),
                        segmentation_method=SegmentationMethod.AI_SPLIT,
                        confidence=0.7,
                    )
                )
            else:
                # Fall back to the full text so review still happens, but
                # flag it clearly so the UI can show reduced confidence.
                note.warnings.append(
                    "AI segmentation did not return this code; reviewing full "
                    "document text instead of an isolated note."
                )
                rebuilt.append(note)
        notes = rebuilt

    result.detected_notes = notes

    for note in notes:
        try:
            guideline_text = load_guideline(note.code, guidelines_dir=guidelines_dir)
        except Exception as exc:
            result.warnings.append(f"Skipped review of {note.code.value}: {exc}")
            continue

        try:
            review = ai_client.review_note(note.code, note.text, guideline_text)
            result.reviews.append(review)
        except Exception as exc:
            result.warnings.append(f"AI review failed for {note.code.value}: {exc}")

    if reverse_map:
        result = rehydrate_result(result, reverse_map)

    return result
