"""
Best-effort PHI/PII redaction layer.

Strips identifiers out of note text BEFORE it's ever sent to a third-party
AI backend, and reverses the substitution afterward so the LOCAL report
still displays real values — the practice is authorized to see its own
client's data; the point is that the third-party AI backend never does.

READ THIS BEFORE RELYING ON IT AS A COMPLIANCE CONTROL:

This is a technical risk-reduction measure, not a legal determination.
Whether a specific redacted note satisfies HIPAA's Safe Harbor
de-identification standard (45 CFR Sec. 164.514(b)(2)) -- and therefore
whether sending it to a non-BAA-covered endpoint is compliant -- depends on
the actual content of your notes and your client population size, not just
this code. In particular:

  - Safe Harbor's 18th category ("any other unique identifying number,
    characteristic, or code") is a catch-all that free-text clinical
    narrative can trip even after names/dates/IDs are removed. A very
    specific combination of details can still be identifying, especially
    at a small practice with few clients.
  - This module reliably redacts (a) values captured from labeled fields it
    recognizes (client name, ID, DOB, provider name, organization,
    insurance ID) wherever they reappear in the document -- including
    inside narrative prose -- and (b) common freeform patterns (emails,
    phone numbers, SSNs, calendar dates, long numeric IDs, IP addresses).
    It does NOT run a general-purpose named-entity-recognition pass, so a
    person's name that appears ONLY in narrative prose (e.g. a sibling
    mentioned in passing) and never in a labeled field will NOT be caught.

Get this reviewed by whoever handles your compliance/legal obligations
before treating de-identification as your compliance posture instead of a
BAA -- this file is engineering, not legal sign-off.
"""

from __future__ import annotations

import re
from dataclasses import replace as dataclass_replace

from .models import DetectedNote, DocumentReviewResult, GuidelineFinding, NoteReview

# --- Labeled-field extraction -----------------------------------------------
#
# (fixed token, candidate label patterns tried in order, value shape)
#
# Label patterns are regexes matched case-insensitively against text like
# "Client Name: Liam Camano", "Client\nLiam Camano", or "Client:\nLiam Camano"
# -- the different real-world vendors we've seen all separate label from
# value differently (same line with a colon, same line with just whitespace,
# or label-then-newline), so the pattern tolerates all three.

# Note: word separator is [ \t]+ (not \s+) so the match can never cross a
# newline into the next labeled field's value — an earlier version used
# \s+ here and greedily swallowed subsequent lines like "Client ID: ...".
_NAME_VALUE = r"[A-Z][A-Za-z'\-\.]+(?:[ \t]+[A-Z][A-Za-z'\-\.]+){0,3}"

#
# The single-word fallback alternatives ("client", "provider", "organization"
# on their own, with no qualifying word like "name") are deliberately
# anchored to the start of a line ((?:^|\n)[ \t]*word). Without that anchor,
# a bare word like "client" matches its first appearance ANYWHERE in the
# document -- including plain narrative prose like "The client engaged
# in..." -- and then swallows whatever capitalized words happen to follow
# as if they were a name. That was observed for real: on one real sample,
# the unanchored bare-"client" fallback matched inside ordinary narrative
# text and never found the actual "Client:" field lower in the document, so
# the real client name was never learned as a value to redact anywhere.
# Anchoring to line-start (while still leaving the colon optional, since
# some vendor templates put the label and value on separate lines with no
# colon at all) filters out the narrative case without breaking the
# label-then-newline layout.
_LABEL_FIELDS: list[tuple[str, list[str], str]] = [
    (
        "[CLIENT_NAME]",
        [r"client\s+name", r"(?:^|\n)[ \t]*client(?!\s*(?:id|diagnosis))"],
        _NAME_VALUE,
    ),
    (
        "[PROVIDER_NAME]",
        [
            r"provider\s+name/credentials",
            r"provider\s+name",
            r"(?:^|\n)[ \t]*provider(?!\s*(?:type|license))",
            r"created/entered in system by",
            r"approved by",
        ],
        _NAME_VALUE,
    ),
    (
        "[ORGANIZATION]",
        [r"organization\s+name", r"(?:^|\n)[ \t]*organization"],
        r"[A-Z][A-Za-z0-9&,'\-\.\s]+?(?=\n|$)",
    ),
    ("[CLIENT_ID]", [r"client\s+id"], r"[A-Za-z0-9\-]+"),
    ("[DOB]", [r"date\s+of\s+birth", r"\bdob\b"], r"\d{1,2}/\d{1,2}/\d{2,4}"),
    ("[INSURANCE_ID]", [r"insurance\s*#", r"insurance\s+id", r"insurance\s+number"], r"[\*A-Za-z0-9\-]+"),
]

# --- Freeform patterns (no labeled field needed) ----------------------------
#
# Applied AFTER labeled-field redaction, so anything already replaced by a
# fixed token above is naturally skipped (the original text is gone).
# Assigned incrementing tokens per category since a document can contain
# multiple distinct values of the same kind (e.g. two different dates).
#
# Boundaries use (?<!\d)/(?!\d) rather than \b: \b only fires at a
# word-char/non-word-char transition, and digit and letter are BOTH word
# characters, so a plain \b fails to match when a number runs directly into
# adjacent text with no separator -- e.g. a PDF text extraction that glues a
# date straight onto the next field's label ("...09/07/2021Insurance #:").
# That's a real pattern seen in real sample PDFs (extraction with no
# whitespace between adjacent form fields), and it silently defeated the
# trailing \b in every pattern below. (?<!\d)/(?!\d) still prevents matching
# the middle of a longer digit run, without requiring a non-word neighbor.

_FREEFORM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")),
    ("SSN", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("DATE", re.compile(r"(?<!\d)\d{1,2}/\d{1,2}/\d{2,4}(?!\d)")),
    ("ID", re.compile(r"(?<!\d)\d{6,}(?!\d)")),
    ("IP", re.compile(r"(?<!\d)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?!\d)")),
]


def _extract_labeled_value(text: str, label_alternatives: list[str], value_pattern: str) -> str | None:
    for label in label_alternatives:
        pattern = re.compile(rf"(?i){label}\s*:?\s*\n?\s*({value_pattern})")
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def redact(text: str) -> tuple[str, dict[str, str]]:
    """Return (redacted_text, reverse_map).

    reverse_map maps each placeholder token back to the real value it
    replaced, so the substitution can be exactly reversed later with
    `rehydrate_text` / `rehydrate_result`.
    """
    reverse_map: dict[str, str] = {}
    redacted = text

    for token, label_alternatives, value_pattern in _LABEL_FIELDS:
        value = _extract_labeled_value(redacted, label_alternatives, value_pattern)
        if value and len(value) >= 2:
            pattern = re.compile(re.escape(value))
            if pattern.search(redacted):
                redacted = pattern.sub(token, redacted)
                reverse_map[token] = value

    for prefix, pattern in _FREEFORM_PATTERNS:
        counter = 1

        def _sub(match: re.Match, prefix: str = prefix) -> str:
            nonlocal counter
            token = f"[{prefix}_{counter}]"
            reverse_map[token] = match.group(0)
            counter += 1
            return token

        redacted = pattern.sub(_sub, redacted)

    return redacted, reverse_map


def rehydrate_text(text: str | None, reverse_map: dict[str, str]) -> str | None:
    if not text:
        return text
    result = text
    for token, value in reverse_map.items():
        result = result.replace(token, value)
    return result


def _rehydrate_finding(finding: GuidelineFinding, reverse_map: dict[str, str]) -> GuidelineFinding:
    return dataclass_replace(
        finding,
        explanation=rehydrate_text(finding.explanation, reverse_map) or "",
        excerpt=rehydrate_text(finding.excerpt, reverse_map),
        suggested_fix=rehydrate_text(finding.suggested_fix, reverse_map),
    )


def _rehydrate_note(note: DetectedNote, reverse_map: dict[str, str]) -> DetectedNote:
    return dataclass_replace(note, text=rehydrate_text(note.text, reverse_map) or "")


def _rehydrate_review(review: NoteReview, reverse_map: dict[str, str]) -> NoteReview:
    return dataclass_replace(
        review,
        note=_rehydrate_note(review.note, reverse_map),
        summary=rehydrate_text(review.summary, reverse_map) or "",
        findings=[_rehydrate_finding(f, reverse_map) for f in review.findings],
    )


def rehydrate_result(result: DocumentReviewResult, reverse_map: dict[str, str]) -> DocumentReviewResult:
    """Return a copy of `result` with every redaction token in its detected
    notes and reviews substituted back to the real values, for local
    display. Does not mutate `result`.
    """
    if not reverse_map:
        return result
    return dataclass_replace(
        result,
        detected_notes=[_rehydrate_note(n, reverse_map) for n in result.detected_notes],
        reviews=[_rehydrate_review(r, reverse_map) for r in result.reviews],
    )
