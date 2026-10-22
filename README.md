# Timbre Pronunciation Studio

A local-first studio for **reusable pronunciation rules** on top of Gnani AI's
Timbre text-to-speech API. Define a rule (`Timbre` → `Tim-ber`), apply it to a
script, keep the canonical script unchanged, and hear the original and adjusted
audio with identical model, voice, language and speed settings.

> **Honest limitation:** this is application-side text substitution, not native
> phoneme/IPA control. It does not claim that Gnani lacks pronunciation
> capability, and it does not claim universal pronunciation correctness. See
> [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

---

## Status

| Area | State |
|---|---|
| FastAPI backend (all documented endpoints) | Implemented, 130 tests passing |
| Rule engine, dictionary store, TTS client, audio cache | Implemented and tested |
| `scripts/smoke_test.py` (Gate A) | **Passed 20 Oct 2026** — both models returned audio |
| Gate B pronunciation POC | **Passed 21 Oct 2026** — 8 of 8 terms judged closer, 0 damaged, settings held constant; one listener, 8 English terms |
| Measured limits (22 Oct 2026) | 800 characters ≈ 6 s and ≈ 4.7 MB — NFR-01 met; exactly 2,000 characters accepted in 9.2 s / 12 MB, so the hard block is verified; 2,100 characters rejected in 133 ms. See `docs/LIMITATIONS.md` — Measured limits |
| Streamlit UI (`streamlit_app/`) | **Not built yet** — chosen 21 Oct 2026 (`docs/TRD.md` §12) |
| README, demo video, public post | This README exists; demo not recorded |

The backend is complete to `docs/Backend Schema.md`. The Streamlit UI is the
remaining MVP work; until it exists the API is usable through `/docs`. If you are
building that UI, start at `docs/Implementation Plan.md` §2.1.

---

## Requirements

- Python 3.10+ (tested on 3.11.9)
- A Gnani API key with programme credits
- No Node, no npm, no build step: the UI is Streamlit (`streamlit>=1.40`, installed
  into the same venv when `streamlit_app/` lands)

## Setup (Windows, bash)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
# open backend/.env and set GNANI_API_KEY
```

`.env` and `data/` are gitignored. The key is never written to disk by the app,
never returned in a response, and never logged.

`GNANI_API_KEY` only has to be **non-empty** for the app to start; it is used only
when audio is generated. Building or reviewing the UI therefore needs a
**placeholder**, not the real key:

```bash
# backend/.env
GNANI_API_KEY=placeholder-not-a-real-key
```

Everything except generation works, and Generate fails cleanly with `401` — which
is the error state worth building against anyway (`TRD` §6.3).

## Run

The whole app is one process and one command, run **from the project root**:

```bash
.venv/Scripts/python.exe -m streamlit run streamlit_app/app.py
```

That works from a fresh terminal with no `cd` and no `PYTHONPATH`, because
`streamlit_app/app.py` puts `backend/` on `sys.path` in its first four lines
(`TRD` §16.2). If those lines are ever removed, use the fallback instead:

```bash
cd backend
../.venv/Scripts/python.exe -m streamlit run ../streamlit_app/app.py
```

The API alone, for `/docs`, the OpenAPI schema and the HTTP tests:

```bash
cd backend
../.venv/Scripts/python.exe -m app.main
# or, with reload:
../.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --reload --port 8000
```

Open <http://127.0.0.1:8000/docs> for the interactive API. A missing
`GNANI_API_KEY` stops startup with the canonical message instead of failing on
the first click.

The Streamlit command above is the demo: one process, one terminal, no build. The
API command is for `/docs`, the OpenAPI schema and the HTTP tests. The app factory
still mounts a `frontend/dist` directory if one ever exists, but nothing in this
project creates it.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness plus `key_configured` (boolean only) |
| `GET` | `/api/options` | Models, voices, fixed language/speed, limits |
| `GET`/`POST` | `/api/dictionaries` | List / create dictionaries |
| `PATCH`/`DELETE` | `/api/dictionaries/{id}` | Rename / delete |
| `GET`/`POST` | `/api/dictionaries/{id}/rules` | List / create rules |
| `PATCH`/`DELETE` | `/api/rules/{id}` | Edit / delete a rule |
| `POST` | `/api/transform` | Apply rules locally — no upstream call, no credits |
| `POST` | `/api/synthesize` | Generate audio (cached) |
| `GET` | `/api/audio/{key}.wav` | Play cached WAV bytes |

Errors use one envelope:

```json
{
  "success": false,
  "error": {
    "type": "VALIDATION_ERROR",
    "message": "Replacement cannot be empty.",
    "details": [{ "field": "replacement", "issue": "empty" }]
  }
}
```

## Tests

```bash
.venv/Scripts/python.exe -m pytest backend -q
```

130 tests cover the rule engine (including every worked example in PRD §8.3), the
dictionary store and its invariants, configuration, the TTS client's failure
mapping (both upstream error shapes), the audio cache key and duration parsing,
the API's error envelope and its validation paths, the transform and synthesize
workflows end to end, the SPA catch-all leaving unknown `/api` paths as 404s,
the POC retry script's caching, listening-sheet logic, credit guard and
dry-run safety, and the limit-measurement script's sample construction and
no-spend path.

## Scripts

None of the three scripts is part of the shipped app.

```bash
# Gate A: prove the API works and save two WAVs
.venv/Scripts/python.exe scripts/smoke_test.py

# Gate B: 8 terms, original vs adjusted, fixed settings (16 WAVs)
.venv/Scripts/python.exe scripts/poc_matrix.py --dry-run   # free preview
.venv/Scripts/python.exe scripts/poc_matrix.py             # uses credits

# Gate B retry: your own respellings, the product's real loop
.venv/Scripts/python.exe scripts/try_respelling.py terms       # the 8 terms
.venv/Scripts/python.exe scripts/try_respelling.py interactive  # type a respelling per term
.venv/Scripts/python.exe scripts/try_respelling.py sheet        # rebuild the listening sheet
.venv/Scripts/python.exe scripts/try_respelling.py verdict --verdict "Zentara=closer|note"

# M10: measure the open limits — 800-char p95 (TQ4) and the real ceiling (TQ5)
.venv/Scripts/python.exe scripts/measure_limits.py --dry-run   # free preview
.venv/Scripts/python.exe scripts/measure_limits.py             # up to 7 credits
```

`poc_matrix.py` writes `data/poc_results.json` and `data/poc_results.md` with a
`verdict` field per term. It was the first attempt; its 8 builder-authored
respellings are kept only as informal evidence of what does not work.

Gate B was closed on 21 Oct 2026 by `try_respelling.py`: 8 of 8 terms judged
closer, 0 damaged, settings held constant. The per-term record is committed as
[`docs/evidence/gate-b-try_results.json`](docs/evidence/gate-b-try_results.json)
(copied from the gitignored `data/try_results.json`), and the read-only summary
is `Implementation Plan` §8.1. The audio itself is local only: 20 WAVs in
`data/audio/try/`, 18 of them referenced by the manifest.

`measure_limits.py` answers the questions `TRD` §20 used to list as open: the
latency of an 800-character request (TQ4, against NFR-01's 10 s p95) and what the
API does at and above the app's 2,000-character block (TQ5 / TQ5b). It sends five
**distinct** 780–800-character scripts (distinct because an identical script would
be answered from cache and time the cache instead of the network), plus ~1,900,
exactly 2,000 and ~2,100 character probes. `--probe ceiling-2000` runs a single
label without discarding the results already in `data/limits_results.json`.

Run, 22 Oct 2026: median 6,157 ms and slowest-of-five 6,905 ms for 800 characters
(**inside the 10 s target**, ~4.7 MB per clip); 1,897 characters accepted in
10,970 ms; exactly 2,000 characters accepted in 9,197 ms — so the block is a
verified ceiling, not a guess; 2,100 characters rejected in 133 ms as a generic
502. Latency turned out not to be monotonic in length. See `docs/LIMITATIONS.md`
— Measured limits.

`try_respelling.py` drives the retry with user-authored respellings. It holds
model, voice, language and speed constant, applies the substitution with the
backend's real rule engine, and reuses an original whenever the sentence and
settings are unchanged, so no sentence is paid for twice. `interactive` prompts
for a respelling per term and rebuilds `data/audio/try/listen.html` after each
one. It never launches a media player: the judgement happens in the browser,
where the original and the adjusted clip sit side by side. Record what you hear
with `verdict --verdict "Zentara=closer|note"`; `sheet` rebuilds the page with
the verdicts on it.

## Credits are guarded

`poc_matrix.py`, `try_respelling.py` and `measure_limits.py` will **not** spend
credits until a human types `spend` at the prompt. They print the maximum number
of paid calls first, and count only audio that is not already cached. A pipe, a
heredoc or an AI agent gets EOF at that prompt and the run cancels with no call
made. `--dry-run` never prompts because it never pays.

`--confirm-spend` skips the prompt for a deliberate scripted run. Do not use it
without saying how many calls it will make. The repository rules for any AI
assistant are in [`AGENTS.md`](AGENTS.md).

## Architecture

```text
backend/app/
  main.py            app factory, error handlers, static mount
  config.py          env loading, limits, fail-fast key check
  errors.py          13-type taxonomy mapped to status codes
  catalogue.py       models and English voices
  deps.py            request-scoped accessors
  api/               health, options, dictionaries, rules, transform,
                     synthesize, audio
  core/
    pronunciation_rules.py   pure rule engine
    dictionary_store.py      atomic per-file JSON persistence
    audio_cache.py           six-input sha256 cache, memory + disk + sidecar
    gnani_tts.py             Timbre client, typed failures, no retries
    atomic.py                temp file + os.replace
  models/schemas.py  Pydantic wire models
  tests/             130 tests + the 7 documented fixtures
scripts/             developer utilities (all guarded against spending)
streamlit_app/       the UI (not built yet)
data/                runtime dictionaries and audio (gitignored)
docs/                PRD, TRD, App Flow, UI/UX, Backend Schema, Plan
```

The rule engine is a single-pass regex substitution over the original string,
longest source first, whole-word boundaries, case-insensitive match with the
replacement inserted verbatim. The original script is never mutated.

## What is left

**Gate B is closed** (21 Oct 2026): 8 of 8 terms judged closer, 0 damaged,
settings held constant. One listener, one session, 8 English terms — a viability
check, not an accuracy rate. Coimbatore improved only partly and is not seeded.

1. The Streamlit UI (`streamlit_app/`, per `docs/TRD.md` §12, built by the
   teammate from 23 Oct). It also carries two must-haves the backend deliberately
   does not: the first-run seed dictionary (`docs/App Flow.md` §5 — the verified
   winners; no code creates it yet) and the visible limitation note (US-09).
2. Demo video and public post with `#GnaniAI` and
   `#GreatIndianAIInternshipChallenge`.

## Docs

- [`docs/PRD.md`](docs/PRD.md) — product requirements and the Gate B stop condition
- [`docs/TRD.md`](docs/TRD.md) — technical design
- [`docs/Backend Schema.md`](docs/Backend%20Schema.md) — the wire contract
- [`docs/App Flow.md`](docs/App%20Flow.md) — user journeys and guardrails
- [`docs/UI-UX Brief.md`](docs/UI-UX%20Brief.md) — design system
- [`docs/Implementation Plan.md`](docs/Implementation%20Plan.md) — milestones
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — known limitations, stated plainly
