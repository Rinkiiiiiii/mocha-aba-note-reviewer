"""
Pluggable AI backend interface.

Everything else in this codebase (pipeline, segmentation fallback) talks to
an AI provider ONLY through the `AIReviewClient` protocol defined here. That
means switching providers — local Ollama today, a hosted API with a signed
BAA once one's chosen, something else entirely later — never requires
touching extraction, detection, segmentation, guidelines, or pipeline code.

Three implementations are provided:

  * `MockAIClient`   — deterministic, no network calls, used in tests and to
                        exercise the full pipeline before any AI backend is
                        wired up. Does NOT do real compliance review.
  * `OllamaClient`    — fully functional against a local Ollama install
                        (http://localhost:11434 by default). No API key
                        needed. Good for developing/testing the pipeline
                        today, and a legitimate production option given the
                        PHI-privacy constraint discussed in the project's
                        architecture notes.
  * `HostedChatClient`— fully functional against any OpenAI-compatible chat
                        completions endpoint (OpenAI, Azure OpenAI, and most
                        other hosted providers speak this API shape). This is
                        the "last step" the project owner will finish by
                        supplying api_key / base_url / model once a provider
                        with an appropriate BAA is chosen.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .models import (
    DetectedNote,
    FindingStatus,
    GuidelineFinding,
    NoteCode,
    NoteReview,
    Severity,
)
from .prompts import (
    REVIEW_SYSTEM_PROMPT,
    SEGMENTATION_SYSTEM_PROMPT,
    build_review_prompt,
    build_segmentation_prompt,
)


class AIBackendError(RuntimeError):
    """Raised when an AI backend call fails or returns something unusable."""


class AIReviewClient(Protocol):
    def segment_document(self, text: str, codes: list[NoteCode]) -> dict[NoteCode, str]:
        """Split `text` into per-code narrative text. Only called when a
        deterministic header-split wasn't possible (see core.segmentation)."""
        ...

    def review_note(self, code: NoteCode, note_text: str, guideline_text: str) -> NoteReview:
        """Review one note's text against its guideline text."""
        ...


# --- Shared response-parsing helpers ----------------------------------------

def _extract_json_object(raw: str) -> dict:
    """Models sometimes wrap JSON in ```json fences or add stray whitespace/
    commentary despite instructions. Strip fences, then grab the first
    balanced {...} block and parse it.
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    if start == -1:
        raise AIBackendError(f"No JSON object found in AI response: {raw!r}")

    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise AIBackendError(f"Malformed JSON from AI response: {exc}\n{candidate}") from exc

    raise AIBackendError(f"Unbalanced JSON braces in AI response: {raw!r}")


def _review_from_json(note: DetectedNote, data: dict) -> NoteReview:
    findings = [
        GuidelineFinding(
            guideline_id=f.get("guideline_id", "unknown"),
            category=f.get("category", "General"),
            status=FindingStatus(f.get("status", "partial")),
            explanation=f.get("explanation", ""),
            excerpt=f.get("excerpt"),
            suggested_fix=f.get("suggested_fix"),
            severity=Severity(f.get("severity", "medium")),
        )
        for f in data.get("findings", [])
    ]
    return NoteReview(
        note=note,
        overall_status=FindingStatus(data.get("overall_status", "partial")),
        summary=data.get("summary", ""),
        findings=findings,
    )


# --- Mock client (tests / pre-integration pipeline exercise) ----------------

class MockAIClient:
    """No network calls, fully deterministic. Lets the rest of the pipeline
    (and its tests) be exercised end-to-end before any real AI backend is
    wired up. `review_note` here does NOT perform real compliance judgment —
    it always returns one placeholder finding saying so, which makes it
    obvious in any output that this was a mock run.
    """

    def segment_document(self, text: str, codes: list[NoteCode]) -> dict[NoteCode, str]:
        # Naive equal-length split, in document order. Good enough to
        # exercise the pipeline; NOT a real segmentation strategy.
        if not codes:
            return {}
        chunk_size = max(1, len(text) // len(codes))
        result = {}
        for i, code in enumerate(codes):
            start = i * chunk_size
            end = len(text) if i == len(codes) - 1 else (i + 1) * chunk_size
            result[code] = text[start:end].strip()
        return result

    def review_note(self, code: NoteCode, note_text: str, guideline_text: str) -> NoteReview:
        note = DetectedNote(code=code, text=note_text)
        return NoteReview(
            note=note,
            overall_status=FindingStatus.PARTIAL,
            summary="Mock review — no AI backend configured yet.",
            findings=[
                GuidelineFinding(
                    guideline_id="mock",
                    category="AI backend not configured",
                    status=FindingStatus.PARTIAL,
                    explanation=(
                        "This is a placeholder review from MockAIClient. Wire up "
                        "OllamaClient or HostedChatClient (see core/ai_client.py) "
                        "to get real guideline-based review results."
                    ),
                    severity=Severity.LOW,
                )
            ],
        )


# --- Ollama (local, free, no API key) ---------------------------------------

class OllamaClient:
    """Calls a local Ollama instance. No API key required, and the note text
    never leaves the machine — see the project's PHI/compliance discussion
    for why that matters here.

    Requires `ollama serve` running locally and the target model pulled
    (e.g. `ollama pull llama3.1`).
    """

    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434", timeout: float = 120.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _generate(self, system_prompt: str, user_prompt: str) -> str:
        import requests  # imported lazily so this module has no hard dep for Mock-only use

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "format": "json",
            },
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except Exception as exc:
            raise AIBackendError(f"Ollama request failed: {exc}") from exc

        payload = response.json()
        return payload.get("response", "")

    def segment_document(self, text: str, codes: list[NoteCode]) -> dict[NoteCode, str]:
        raw = self._generate(SEGMENTATION_SYSTEM_PROMPT, build_segmentation_prompt(text, codes))
        data = _extract_json_object(raw)
        return {NoteCode(k): v for k, v in data.items() if k in {c.value for c in codes}}

    def review_note(self, code: NoteCode, note_text: str, guideline_text: str) -> NoteReview:
        raw = self._generate(REVIEW_SYSTEM_PROMPT, build_review_prompt(code, note_text, guideline_text))
        data = _extract_json_object(raw)
        note = DetectedNote(code=code, text=note_text)
        return _review_from_json(note, data)


# --- Hosted, OpenAI-compatible chat completions API -------------------------

class HostedChatClient:
    """Calls any OpenAI-compatible chat completions endpoint. This shape is
    spoken by OpenAI itself, Azure OpenAI, and most other hosted providers,
    so this one class covers whichever provider ends up chosen — just supply
    the right api_key / base_url / model.

    IMPORTANT (carried over from the project's architecture discussion): if
    real client PHI will be sent here, `base_url` must point at a deployment
    actually covered by a signed BAA (e.g. an Azure OpenAI resource, not a
    bare consumer OpenAI API key) — this class does not enforce that, it's a
    deployment/legal decision, not a code one.
    """

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 120.0):
        if not api_key:
            raise ValueError("HostedChatClient requires an api_key.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        import requests

        # Note: deliberately no "temperature" field. Some models (including
        # the GPT-5.6 family as of this writing) reject any value other than
        # their default and return a 400 if one is sent — omitting it lets
        # each model use its own default rather than hard-coding an
        # assumption that may not hold across providers/models.
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        if not response.ok:
            raise AIBackendError(
                f"Hosted chat request failed: {response.status_code} {response.reason} — {response.text[:1000]}"
            )

        payload = response.json()
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIBackendError(f"Unexpected response shape from hosted API: {payload}") from exc

    def segment_document(self, text: str, codes: list[NoteCode]) -> dict[NoteCode, str]:
        raw = self._chat(SEGMENTATION_SYSTEM_PROMPT, build_segmentation_prompt(text, codes))
        data = _extract_json_object(raw)
        return {NoteCode(k): v for k, v in data.items() if k in {c.value for c in codes}}

    def review_note(self, code: NoteCode, note_text: str, guideline_text: str) -> NoteReview:
        raw = self._chat(REVIEW_SYSTEM_PROMPT, build_review_prompt(code, note_text, guideline_text))
        data = _extract_json_object(raw)
        note = DetectedNote(code=code, text=note_text)
        return _review_from_json(note, data)
