"""
Splitting a document's text into one or more per-code notes.

Real-world evidence (see project architecture notes) confirms a single
document can legitimately contain two distinct notes (e.g. a combined
97155 + 97156 visit). When that happens, some vendors give each note its own
clearly labeled section header (e.g. "... (CPT® Code 97155):"), and some
presumably won't. This module:

  1. Tries a deterministic header-based split first, since it's cheap,
     free, and fully explainable when it works.
  2. Falls back to marking the notes UNRESOLVED when it doesn't, so the
     pipeline knows to hand the job to the AI client's `segment_document`
     instead of guessing with more regex.

Hand-writing per-vendor splitting rules was explicitly the thing we wanted
to avoid, so step 2 is a deliberate handoff to semantic understanding
rather than an attempt to cover every possible template here.
"""

from __future__ import annotations

import re

from .models import DetectedNote, NoteCode, SegmentationMethod

# Matches things like "(CPT® Code 97155)", "(CPT Code: 97156)", "CPT Code 97153"
# case-insensitively, tolerant of the registered-trademark symbol and minor
# punctuation variation.
_HEADER_MARKER_PATTERN = re.compile(
    r"(?i)cpt\s*(?:®|\(r\))?\s*code[:\s]*\(?\s*(97153|97155|97156)\s*\)?"
)


def _find_header_start_positions(text: str) -> dict[NoteCode, int]:
    """Earliest position (start of that line) where each code appears inside
    a "CPT Code XXXXX"-style section header, if present at all.
    """
    positions: dict[NoteCode, int] = {}
    for match in _HEADER_MARKER_PATTERN.finditer(text):
        code = NoteCode(match.group(1))
        if code not in positions:
            line_start = text.rfind("\n", 0, match.start()) + 1
            positions[code] = line_start
    return positions


def segment_into_notes(text: str, codes: list[NoteCode]) -> list[DetectedNote]:
    """Split `text` into one DetectedNote per code in `codes`.

    - Zero codes -> empty list (caller should treat this as "nothing to review").
    - One code -> the whole document is that one note.
    - 2+ codes -> try header-split; if that doesn't cleanly account for every
      detected code, return UNRESOLVED placeholders (full text, zero
      confidence) for the pipeline to send through AI-assisted segmentation.
    """
    if not codes:
        return []

    if len(codes) == 1:
        return [
            DetectedNote(
                code=codes[0],
                text=text.strip(),
                segmentation_method=SegmentationMethod.SINGLE_CODE,
                confidence=1.0,
            )
        ]

    header_positions = _find_header_start_positions(text)

    if all(code in header_positions for code in codes):
        ordered = sorted(
            ((code, pos) for code, pos in header_positions.items() if code in codes),
            key=lambda pair: pair[1],
        )
        notes: list[DetectedNote] = []
        for i, (code, start) in enumerate(ordered):
            end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
            section_text = text[start:end].strip()
            notes.append(
                DetectedNote(
                    code=code,
                    text=section_text,
                    segmentation_method=SegmentationMethod.HEADER_SPLIT,
                    confidence=0.9,
                )
            )
        return notes

    # No clean, complete header split available -> defer to AI segmentation.
    return [
        DetectedNote(
            code=code,
            text=text,
            segmentation_method=SegmentationMethod.UNRESOLVED,
            confidence=0.0,
            warnings=[
                f"No distinct section header found for code {code.value}; "
                "this document needs AI-assisted segmentation before review."
            ],
        )
        for code in codes
    ]


def needs_ai_segmentation(notes: list[DetectedNote]) -> bool:
    """True if any note in the list is a placeholder still awaiting
    AI-assisted segmentation (i.e. header-split wasn't possible)."""
    return any(n.segmentation_method == SegmentationMethod.UNRESOLVED for n in notes)
