"""
Core note-review engine for the Mocha ABA Note Reviewer.

This package is intentionally UI-agnostic: nothing in here knows or cares
whether it's being called from a desktop app (pywebview), a CLI, or a future
web service. The only public entry point most callers need is
`core.pipeline.review_document`.
"""
