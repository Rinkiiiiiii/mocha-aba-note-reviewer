# Mocha ABA Note Reviewer

File in, structured ABA-guideline review(s) out, shown in a native-feeling
dark desktop app. Split into two layers on purpose:

- `core/` — the UI-agnostic backend. File in, structured review(s) out.
  Zero UI dependency, fully unit tested.
- `desktop/` — a pywebview desktop shell wrapped around
  `core.pipeline.review_document`. Thin by design: almost all of its logic
  is also unit tested (see "Running the desktop app" below for the one part
  that isn't and why).

## Layout

```
core/
  models.py        Data classes: NoteCode, DetectedNote, GuidelineFinding, NoteReview, DocumentReviewResult
  extraction.py     PDF/DOCX -> plain text, strips DocuSign "Certificate of Completion" boilerplate
  detection.py      Finds which of 97153/97155/97156 appear anywhere in the text
  segmentation.py   Splits a document into one note per code (header-split, or flags for AI segmentation)
  guidelines.py     Loads guideline text per code from guidelines/*.md
  prompts.py        Shared prompt text for AI segmentation + review calls
  ai_client.py      AIReviewClient interface + MockAIClient, OllamaClient, HostedChatClient
  deidentify.py     Best-effort redaction: strips recognizable identifiers before the AI call, restores them locally afterward
  pipeline.py       review_document() — ties all of the above together
  report.py         DocumentReviewResult -> dark-themed HTML / clean Markdown

guidelines/
  97153.md, 97155.md, 97156.md   Real documentation criteria, transcribed from
  the CASP (Council of Autism Service Providers) Session Note Template
  Guidance for each code, as provided by the practice.

desktop/
  config.py         Local, on-device storage for the OpenAI API key + model choice (never in this repo)
  api.py            DesktopAPI — the Python bridge exposed to the JS frontend as window.pywebview.api
  pages.py          HTML for the home/settings screens (dark theme, matches core/report.py)
  main.py           Entry point: creates the pywebview window, starts the app — run with `python -m desktop.main`

scripts/
  run_review.py       CLI: review one file with mock/ollama/hosted backend, print Markdown or write HTML
  compare_tiers.py     CLI: run the same note through multiple GPT-5.6 tiers and print a side-by-side comparison

tests/              61 tests, synthetic (non-PHI) fixtures generated on the fly
```

## Status

The core engine and the desktop UI are both built and tested (61 tests).
Real guideline content is wired up, de-identification is on by default, and
the AI backend defaults to GPT-5.6 Terra. What's left is for you to run the
app on your own machine and add your API key in its Settings screen — see
"Running the desktop app" below.

## Running the tests

```
pip install -r requirements.txt -r desktop/requirements.txt
pytest
```

61 tests cover: DocuSign boilerplate stripping, code detection across
different field placements/labels (confirmed against real sample notes from
two different vendors), header-based multi-note segmentation, the
AI-segmentation fallback path, full pipeline orchestration (now against the
real CASP-derived guideline content by default), HTML/Markdown report
rendering (including an XSS-style escaping check for the embedded
copy-as-markdown payload), the redaction/rehydration round-trip in
`core/deidentify.py` (including a pipeline-level test that spies on what the
AI client actually receives, to prove the real client name never reaches
it), local API-key config storage, and the desktop bridge (`DesktopAPI`) —
file picking, settings, and the full review flow — tested against fakes.

## Running the desktop app

```
pip install -r requirements.txt -r desktop/requirements.txt
python -m desktop.main
```

On first launch: click the settings gear, paste your OpenAI API key, and
save — it's written to a small config file in your own home directory
(`~/.mocha_aba_reviewer/config.json`, owner-read/write only), never into
this repo or anything you'd share. Then go back and click the drop zone to
pick a PDF or Word note; the report replaces the window when it's done, with
a "New review" button to go again.

**Linux only:** pywebview needs a GTK or Qt Python binding to actually open
a window — see the comments in `desktop/requirements.txt` for the one-line
install for your distro. Windows/macOS don't need anything extra; pywebview
uses the OS's built-in WebView2/WKWebView.

A note on how this was built and verified: `desktop/api.py` (the bridge
between the native window and the Python pipeline) and `desktop/config.py`
are fully unit tested — 20 of the 61 tests — using fake file dialogs and a
fake "window loader" so the actual logic (status handling, error messages,
the redaction-enabled review call, navigation between screens) is verified
without needing a real window. `desktop/main.py` itself — the few lines that
call `webview.create_window(...)` and `webview.start()` — could not be
exercised the same way: this was built in a cloud sandbox with no display
and no GTK/Qt Python bindings installed, so there was no way to actually
open and click through the native window here. That file is deliberately as
thin as possible so there's very little left to go wrong once it's run
somewhere that does have a display — but it's worth clicking through it
yourself on first run rather than assuming it's flawless.

## De-identification (avoiding a BAA requirement for now)

`core.pipeline.review_document(..., deidentify=True)` — the default — runs
every note through `core.deidentify.redact()` before it's sent to the AI
backend, and reverses the substitution afterward so the report you see
locally still shows real values. It:

- Extracts known values from labeled fields (client name, client ID, DOB,
  provider name, organization, insurance ID) and replaces every literal
  occurrence of each value anywhere in the document — including inside
  narrative prose, not just the labeled field itself — with a fixed token
  like `[CLIENT_NAME]`.
- Separately catches common freeform patterns wherever they appear: emails,
  phone numbers, SSNs, calendar dates, long numeric IDs, IP addresses.
- Reverses all of this locally before you ever see the review, via
  `rehydrate_result()`.

**This is a risk-reduction engineering control, not a legal determination
that a BAA is unnecessary.** It was validated structurally against the 5
real sample notes originally provided for this project (checking, without
ever printing the real values themselves, whether each known identifier in
each sample was successfully redacted). The result: most labeled-field
identifiers across all 5 real samples were caught, but a few were not,
specifically:

- A name that appears **only** inline near a signature/timestamp line
  (e.g. `"11:45 am EDT (Full Name) 97155"`) and nowhere in a recognized
  labeled field — the module never learns that value exists, so it can't
  strip it from anywhere else in the document either.
- A name mentioned only in narrative prose with no labeled field backing it
  at all (e.g. a passing narrative mention with no "Client:"/"Provider:"
  field ever containing that exact string).
- One vendor's PDF text extraction ran adjacent form fields together with no
  separating whitespace or newline (e.g. a date immediately followed by the
  next field's label with no space between them), which can defeat the
  labeled-field matching for that specific layout.

In short: this module does **not** do general-purpose named-entity
recognition, so it can miss identifying information that never appears in a
field it recognizes. Given a small client population, HIPAA's Safe Harbor
catch-all category (any other unique identifying detail/characteristic) is
also a real consideration for free-text narrative even after known fields
are stripped. Get this reviewed by whoever handles your compliance/legal
obligations before treating de-identification as a substitute for a signed
BAA — this is engineering, not legal sign-off. Set `deidentify=False` on
`review_document()` to send full, un-redacted text (e.g. once BAA coverage
is confirmed and you'd rather skip the redaction step entirely).

## Wiring in the AI backend

1. Guideline content is in place (see above) — no action needed there.
2. Pick a backend:
   - **Local, free, most private**: `OllamaClient(model="llama3.1")` — needs
     `ollama serve` running locally with the model pulled. No API key.
   - **Hosted API (OpenAI GPT-5.6)**: `HostedChatClient(api_key=..., base_url="https://api.openai.com/v1", model="gpt-5.6-terra")`
     — the three tiers are `gpt-5.6-luna` (cheapest/fastest, but meaningfully
     weaker long-context recall — see the tier-comparison note in
     architecture-decisions.md before defaulting to it for this document-analysis
     task), `gpt-5.6-terra` (balanced, currently the recommended default),
     and `gpt-5.6-sol` (flagship). `HostedChatClient` also works with any other
     OpenAI-compatible endpoint (Azure OpenAI, etc.) by changing `base_url`.
     **If real client PHI will be sent here, `base_url` must point at a
     deployment actually covered by a signed BAA** — a bare OpenAI consumer API
     key is not sufficient on its own; see architecture-decisions.md.
3. Call `core.pipeline.review_document(path, your_client)` — or use
   `scripts/run_review.py` / `scripts/compare_tiers.py` to test from the
   command line without writing any code.

No other code needs to change — that's the whole point of the
`AIReviewClient` interface.

## A note on the multi-code segmentation fallback

When a document contains two codes and there's no clean per-code section
header to split on, `segment_into_notes` returns UNRESOLVED placeholders and
`review_document` calls `ai_client.segment_document(...)` to do the split
semantically instead. This was a deliberate choice over hand-writing more
regex: real samples showed code placement and section structure both vary
across vendors, and language understanding generalizes across that variation
far better than more pattern-matching would.
