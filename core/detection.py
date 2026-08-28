"""
Billing-code detection.

Deliberately dumb and deliberately robust: it does not care where on the
page, in which field, or under which label a code appears. It just searches
the fully extracted plain text for the three known code tokens. This is what
makes detection work identically across differently-templated vendors (see
`architecture-decisions.md` in the project for the real-sample evidence).
"""

from __future__ import annotations

import re

from .models import NoteCode

# Bounded by non-digits on either side so "197153" or "971530" don't
# false-positive match "97153".
_CODE_PATTERN = re.compile(r"(?<!\d)(97153|97155|97156)(?!\d)")


def detect_codes(text: str) -> list[NoteCode]:
    """Return the distinct billing codes found in `text`, in first-appearance
    order, deduplicated.
    """
    found: list[NoteCode] = []
    for match in _CODE_PATTERN.finditer(text):
        code = NoteCode(match.group(1))
        if code not in found:
            found.append(code)
    return found


def detect_code_occurrences(text: str, context_chars: int = 60) -> list[dict]:
    """Return every raw occurrence of a code with surrounding context.

    Not used by the main pipeline, but useful for debugging/auditing why a
    particular document was (or wasn't) recognized, and handy in tests.
    """
    occurrences = []
    for match in _CODE_PATTERN.finditer(text):
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        occurrences.append(
            {
                "code": match.group(1),
                "position": match.start(),
                "context": text[start:end].replace("\n", " ").strip(),
            }
        )
    return occurrences
