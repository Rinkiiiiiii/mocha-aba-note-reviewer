"""
Data models shared across the note-review engine.

Kept deliberately plain (stdlib dataclasses/enums only) so this module has
zero dependencies and can be imported by extraction, detection, segmentation,
guidelines, ai_client, pipeline, and report without ever risking a circular
import or a UI-framework dependency leaking in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NoteCode(str, Enum):
    """The three CPT billing codes this tool recognizes.

    Values are the literal code strings so `NoteCode("97153") is NoteCode.RBT`
    and `str(NoteCode.RBT) == "97153"` (via .value) both work naturally.
    """

    RBT = "97153"
    SUPERVISION = "97155"
    PARENT_TRAINING = "97156"


# Human-readable labels for UI display and prompt construction.
NOTE_CODE_LABELS: dict[NoteCode, str] = {
    NoteCode.RBT: "RBT Note / Direct Treatment (97153)",
    NoteCode.SUPERVISION: "Supervision / Protocol Modification (97155)",
    NoteCode.PARENT_TRAINING: "Parent / Caregiver Training (97156)",
}


class SegmentationMethod(str, Enum):
    """How a DetectedNote's text was isolated from the rest of the document."""

    SINGLE_CODE = "single_code"       # only one code in the doc; whole doc is the note
    HEADER_SPLIT = "header_split"     # multiple codes, split via explicit per-code section headers
    AI_SPLIT = "ai_split"             # multiple codes, no clean headers -> AI was asked to segment
    UNRESOLVED = "unresolved"         # multiple codes detected but segmentation not yet performed


class FindingStatus(str, Enum):
    MET = "met"
    PARTIAL = "partial"
    NOT_MET = "not_met"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class DetectedNote:
    """One logical note extracted from a source document.

    A single uploaded document produces one DetectedNote per distinct billing
    code found in it (usually one, sometimes two).
    """

    code: NoteCode
    text: str
    segmentation_method: SegmentationMethod = SegmentationMethod.SINGLE_CODE
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return NOTE_CODE_LABELS[self.code]


@dataclass
class GuidelineFinding:
    """A single guideline-compliance finding for one note."""

    guideline_id: str
    category: str
    status: FindingStatus
    explanation: str
    excerpt: Optional[str] = None
    suggested_fix: Optional[str] = None
    severity: Severity = Severity.MEDIUM


@dataclass
class NoteReview:
    """The full AI-generated review of a single DetectedNote."""

    note: DetectedNote
    overall_status: FindingStatus
    summary: str
    findings: list[GuidelineFinding] = field(default_factory=list)


@dataclass
class DocumentReviewResult:
    """Top-level result returned by `core.pipeline.review_document`."""

    source_filename: str
    detected_notes: list[DetectedNote] = field(default_factory=list)
    reviews: list[NoteReview] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def note_count(self) -> int:
        return len(self.detected_notes)
