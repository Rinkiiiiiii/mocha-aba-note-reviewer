"""
Loading the guideline text each note type is reviewed against.

Deliberately just a file loader: the actual regulatory/billing-compliance
criteria for each code are domain content that needs to come from you (or
whatever authoritative source you're reviewing notes against), not something
this tool should invent. See the placeholder files under `guidelines/` —
fill each one in with the real criteria before running review_note for real.
"""

from __future__ import annotations

from pathlib import Path

from .models import NoteCode

# Repo layout assumption: guidelines/ sits alongside core/ at the project root.
_GUIDELINES_DIR = Path(__file__).resolve().parent.parent / "guidelines"

_FILENAMES: dict[NoteCode, str] = {
    NoteCode.RBT: "97153.md",
    NoteCode.SUPERVISION: "97155.md",
    NoteCode.PARENT_TRAINING: "97156.md",
}


class GuidelineNotConfiguredError(RuntimeError):
    """Raised when a guideline file is missing or still just the placeholder."""


_PLACEHOLDER_MARKER = "<!-- PLACEHOLDER"


def load_guideline(code: NoteCode, *, guidelines_dir: Path | None = None) -> str:
    """Return the guideline text for `code`.

    Raises GuidelineNotConfiguredError if the file is missing or hasn't been
    filled in yet, so a misconfigured review fails loudly instead of quietly
    reviewing notes against an empty/placeholder ruleset.
    """
    directory = guidelines_dir or _GUIDELINES_DIR
    path = directory / _FILENAMES[code]

    if not path.exists():
        raise GuidelineNotConfiguredError(
            f"No guideline file found for {code.value} at {path}."
        )

    text = path.read_text(encoding="utf-8")
    if _PLACEHOLDER_MARKER in text:
        raise GuidelineNotConfiguredError(
            f"{path} is still a placeholder — fill it in with the actual "
            f"{code.value} guideline/compliance criteria before running a real review."
        )
    return text
