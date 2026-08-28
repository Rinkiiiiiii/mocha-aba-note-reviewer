#!/usr/bin/env python3
"""
CLI harness for testing the review pipeline end-to-end before the desktop UI
exists. Prints a Markdown report to stdout (or writes an HTML report to a
file with --html-out).

Examples:

  # Local, free, no API key (requires `ollama serve` running):
  python3 scripts/run_review.py note.pdf --backend ollama --model llama3.1

  # Hosted OpenAI-compatible API (reads OPENAI_API_KEY from the environment
  # by default so the key never has to be typed on the command line):
  export OPENAI_API_KEY=sk-...
  python3 scripts/run_review.py note.pdf --backend hosted --model gpt-5.6-terra

Never pass --api-key on the command line in a shared/logged shell — prefer
the OPENAI_API_KEY environment variable, which this script reads by default.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ai_client import HostedChatClient, MockAIClient, OllamaClient
from core.pipeline import review_document
from core.report import render_html, render_markdown


def build_client(args):
    if args.backend == "mock":
        return MockAIClient()
    if args.backend == "ollama":
        return OllamaClient(model=args.model or "llama3.1", base_url=args.base_url or "http://localhost:11434")
    if args.backend == "hosted":
        api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit(
                "No API key found. Set the OPENAI_API_KEY environment variable "
                "(preferred) or pass --api-key."
            )
        return HostedChatClient(
            api_key=api_key,
            base_url=args.base_url or "https://api.openai.com/v1",
            model=args.model or "gpt-5.6-terra",
        )
    raise SystemExit(f"Unknown backend: {args.backend}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="PDF or DOCX note to review")
    parser.add_argument("--backend", choices=["mock", "ollama", "hosted"], default="hosted")
    parser.add_argument("--model", default=None, help="e.g. gpt-5.6-luna / gpt-5.6-terra / gpt-5.6-sol / llama3.1")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None, help="Prefer the OPENAI_API_KEY env var instead.")
    parser.add_argument("--guidelines-dir", type=Path, default=None)
    parser.add_argument("--html-out", type=Path, default=None, help="Write an HTML report here instead of printing Markdown.")
    args = parser.parse_args()

    client = build_client(args)
    result = review_document(args.file, client, guidelines_dir=args.guidelines_dir)

    if args.html_out:
        args.html_out.write_text(render_html(result), encoding="utf-8")
        print(f"Wrote HTML report to {args.html_out}")
    else:
        print(render_markdown(result))


if __name__ == "__main__":
    main()
