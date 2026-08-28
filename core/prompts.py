"""
Prompt construction shared by every AIReviewClient implementation.

Kept in one place so switching providers (Ollama <-> a hosted API) can never
accidentally change what's actually being asked of the model.
"""

from __future__ import annotations

import json

from .models import NoteCode, NOTE_CODE_LABELS

SEGMENTATION_SYSTEM_PROMPT = (
    "You split multi-code ABA billing documents into their component notes. "
    "You will be given the full text of one document and the CPT billing "
    "codes it contains. Some documents contain two separate service notes "
    "(e.g. a supervision visit and a parent-training visit billed together). "
    "Your job is ONLY to figure out which portion of the text belongs to "
    "which code — do not summarize, evaluate, or omit content. Every "
    "sentence in the source document should end up attributed to exactly "
    "one code. Respond with ONLY a JSON object, no commentary, no markdown "
    "fences, mapping each code to its full verbatim narrative text."
)


def build_segmentation_prompt(text: str, codes: list[NoteCode]) -> str:
    code_list = ", ".join(f'"{c.value}"' for c in codes)
    schema_example = json.dumps({c.value: "<verbatim text belonging to this note>" for c in codes}, indent=2)
    return (
        f"Codes present in this document: {code_list}\n\n"
        f"Return a JSON object shaped exactly like this (values are illustrative):\n"
        f"{schema_example}\n\n"
        f"--- DOCUMENT TEXT START ---\n{text}\n--- DOCUMENT TEXT END ---"
    )


REVIEW_SYSTEM_PROMPT = (
    "You are an ABA (Applied Behavior Analysis) documentation compliance "
    "reviewer. You will be given the guideline/criteria text for one CPT "
    "billing code and the text of one clinical note billed under that code. "
    "Evaluate the note against the guideline text ONLY — do not invent "
    "requirements that aren't stated in the guideline. For each distinct "
    "requirement or common deficiency mentioned in the guideline, produce "
    "one finding describing whether the note meets it, is partial, or "
    "misses it entirely, quoting the relevant excerpt from the note where "
    "possible and suggesting a concrete fix. Respond with ONLY a JSON "
    "object, no commentary, no markdown fences, matching this shape:\n"
    + json.dumps(
        {
            "overall_status": "met | partial | not_met",
            "summary": "1-3 sentence plain-language summary of overall compliance",
            "findings": [
                {
                    "guideline_id": "short slug identifying which requirement this is",
                    "category": "short human-readable category label",
                    "status": "met | partial | not_met",
                    "explanation": "why this status was assigned",
                    "excerpt": "verbatim excerpt from the note this finding is about, or null",
                    "suggested_fix": "concrete rewording/addition to bring it into compliance, or null",
                    "severity": "low | medium | high",
                }
            ],
        },
        indent=2,
    )
)


def build_review_prompt(code: NoteCode, note_text: str, guideline_text: str) -> str:
    return (
        f"CPT Code: {code.value} — {NOTE_CODE_LABELS[code]}\n\n"
        f"--- GUIDELINE TEXT START ---\n{guideline_text}\n--- GUIDELINE TEXT END ---\n\n"
        f"--- NOTE TEXT START ---\n{note_text}\n--- NOTE TEXT END ---"
    )
