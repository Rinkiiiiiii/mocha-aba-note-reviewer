#!/usr/bin/env python3
"""
Run the same note through multiple GPT-5.6 tiers and print a side-by-side
comparison, to help decide which tier is actually good enough for review
quality (see the cost-vs-quality discussion in architecture-decisions.md —
Luna's long-context recall is meaningfully weaker than Terra/Sol's, which
matters for a document-analysis task like this one).

Reads the API key from OPENAI_API_KEY — never pass it on the command line.

Example:
  export OPENAI_API_KEY=sk-...
  python3 scripts/compare_tiers.py note.pdf --tiers luna terra sol
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ai_client import HostedChatClient
from core.pipeline import review_document
from core.report import render_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--tiers", nargs="+", default=["luna", "terra", "sol"], choices=["luna", "terra", "sol"])
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--guidelines-dir", type=Path, default=None)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENAI_API_KEY before running this script.")

    print(f"Comparing tiers on: {args.file.name}\n")

    summary_rows = []
    for tier in args.tiers:
        model = f"gpt-5.6-{tier}"
        client = HostedChatClient(api_key=api_key, base_url=args.base_url, model=model)
        result = review_document(args.file, client, guidelines_dir=args.guidelines_dir)

        print("=" * 80)
        print(f"TIER: {tier}  (model={model})")
        print("=" * 80)
        print(render_markdown(result))
        print()

        total_findings = sum(len(r.findings) for r in result.reviews)
        high_severity = sum(1 for r in result.reviews for f in r.findings if f.severity.value == "high")
        summary_rows.append((tier, len(result.reviews), total_findings, high_severity, len(result.warnings)))

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'tier':<8} {'notes reviewed':<16} {'total findings':<16} {'high severity':<15} {'warnings'}")
    for tier, notes, findings, high, warnings in summary_rows:
        print(f"{tier:<8} {notes:<16} {findings:<16} {high:<15} {warnings}")


if __name__ == "__main__":
    main()
