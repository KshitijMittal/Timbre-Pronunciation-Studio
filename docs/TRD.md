# Timbre Pronunciation Studio — Technical Requirements Document

| Field | Value |
|---|---|
| Document | TRD |
| Version | 1.0 |
| Date | 20 October 2026 |
| Status | Approved — binding, amended 22 October 2026 |
| Parent document | `docs/PRD.md` v1.0 |
| Owners | [You] — backend, rule engine, TTS client, tests; [Teammate] — Streamlit UI, README, demo video |
| Target release | Feature freeze 6 November 2026; submission 10 November 2026 |
| Supersedes | The `src/`-only layout proposed in the project handoff dossier (replaced by a two-stack layout, see §4) |

---

## 1. Purpose and scope

This document specifies **how** Timbre Pronunciation Studio is built. It converts the requirements in `docs/PRD.md` into an implementable technical design: architecture, module boundaries, API contract, algorithms, error handling, configuration, testing and build/run procedures.

It does **not** restate product rationale. Where a requirement is referenced, the PRD ID is given (e.g. FR-23).

**In scope:** MVP architecture through the 6 November feature freeze.
**Out of scope:** the Stretch requirements (FR-13, FR-14, FR-15, FR-28, FR-29) are designed for but not implemented before freeze.

---

## 2. Design principles

1. **The key never leaves the machine.** The API key is read from `backend/.env` by the local Python process — FastAPI in API mode, Streamlit in UI mode. It is never returned in a response, never logged, and never reaches a browser.
2. **The canonical script is immutable.** Transformation is a pure function producing a new string; the original is never mutated, stored in place of, or sent to the API.
3. **Correctness lives in Python.** The rule engine is the product's core and is unit-tested. The frontend displays results; it does not compute them.
4. **No silent credit spend.** Synthesis occurs only on an explicit POST from an explicit user action.
5. **One process for the demo, two for development.** Never ship a demo that needs two terminals.
6. **Fail loudly, locally.** Errors surface with HTTP status and a plain-language cause; nothing is swallowed.
7. **Reversible presentation layer.** The UI imports `core/` and the HTTP API exposes the same core, so either can be replaced without touching domain logic.

---

## 3. System architecture

### 3.1 Component diagram

```text
┌─────────────────────────────────────────────────────────────┐
│ Streamlit UI   (one local Python process)                   │
│  streamlit_app/app.py                                       │
│   ├─ sidebar   dictionaries, voice                          │
│   ├─ settings  model / voice (language, speed fixed)        │
│   ├─ editor    script, character counter, limit state       │
│   ├─ preview   original vs transformed, match report        │
│   └─ audio     Generate, two waveform players               │
└──────────────────────────┬──────────────────────────────────┘
                           │ in-process imports (no HTTP, no CORS)
┌──────────────────────────▼──────────────────────────────────┐
│ core/           Domain logic (no HTTP knowledge)            │
│   pronunciation_rules.py   ← the product's core             │
│   dictionary_store.py      ← JSON persistence               │
│   gnani_tts.py             ← HTTP client to Gnani           │
│   audio_cache.py           ← disk cache + sidecar, pay-once helper  │
│   atomic.py                ← unique temp file + locked replace      │
└──────────────────────────┬──────────────────────────────────┘
(`config.py` — env loading and limits — and `errors.py` — the typed error
taxonomy — sit beside `core/` in `backend/app/`, because both the UI and the
HTTP layer need them.)
                           │ HTTPS  POST /api/v1/tts/inference
                           │ header: X-API-Key-ID
┌──────────────────────────▼──────────────────────────────────┐
│ Gnani Timbre TTS API   https://api.vachana.ai               │
└─────────────────────────────────────────────────────────────┘

Alongside the UI, `backend/app/api/` exposes the same core over HTTP/JSON
(uvicorn). That API is the documented integration contract
(`docs/Backend Schema.md`) and stays maintained and tested; the Streamlit UI
does not need it to run.

Local filesystem (server side):
  data/dictionaries/*.json     ← one file per dictionary
  data/audio/*.wav             ← generated audio for inspection
```

### 3.2 Runtime modes

| Mode | Processes | How it runs |
|---|---|---|
| **Development** | 1 | `streamlit run streamlit_app/app.py` — Streamlit's own dev server, auto-reload on save |
| **Demo / release** | 1 | The same command. Nothing is built, nothing is served from a second port |
| **API / contract** | 1 (optional) | `uvicorn app.main:create_app --factory` in `backend/` — `/docs`, the OpenAPI schema and the HTTP tests |

The single-process demo is a hard requirement, not an optimisation. Keeping the
UI in-process removes CORS, ports, proxies and a build step from the live demo.

### 3.3 Why this split

| Decision | Reason |
|---|---|
| Streamlit over React | Decided 21 Oct 2026: the teammate builds the UI, and Streamlit is one Python file against an already-tested core. No Node, no build, no proxy, one process to demo. The React plan is kept in §13 as the rejected alternative. |
| Python owns the rule engine | The engine must be unit-tested and is the defensible technical contribution. |
| UI imports `core/` in-process | One source of truth for matching, caching and validation, and no HTTP layer between the UI and the logic it is demonstrating. The HTTP API is kept as the documented contract. |
| No database | Single local user, tens of dictionaries, no concurrent writers. JSON is sufficient and human-readable. |

---

## 4. Technology stack

| Layer | Choice | Version floor | Notes |
|---|---|---|---|
| Language (backend) | Python | 3.10 | Matches the official SDK requirement if it is ever adopted |
| Web framework | FastAPI | 0.110 | Async-capable, Pydantic validation, auto OpenAPI docs at `/docs` |
| ASGI server | uvicorn | 0.27 | `--reload` in dev |
| HTTP client | `requests` | 2.31 | Explicit control over headers, timeout and binary handling |
| Config | `python-dotenv` | 1.0 | Loads `.env` into `os.environ` |
| Validation | Pydantic (via FastAPI) | 2.x | Request/response models |
| Testing | pytest | 8.x | Backend only |
| Frontend | Streamlit | 1.40+ | One Python process; no Node, no build step, no bundler |
| Frontend test | pytest AppTest | 8.x | Streamlit's own app-testing harness, same test runner as the backend |
| Styling | Streamlit defaults + small CSS block | — | Theming is limited; see `UI-UX Brief` §16.1 for what is dropped |

### 4.1 Rejected alternatives

| Option | Why rejected |
|---|---|
| `gnani-vachana` SDK | Adds a dependency whose request shaping and error objects we do not control; ~40 lines of `requests` gives clearer failures. |
| React + Vite | Rejected on 21 Oct 2026. Two toolchains, a build step, CORS and a proxy to demo a local single-user tool. The teammate builds the UI in Streamlit instead (§13). |
| SQLite | Schema/migration overhead with no query need; JSON is diffable and directly exportable. |
| Tailwind / MUI | Extra dependency and build surface for a five-panel single-page app. |
| HTML/CSS injected into Streamlit (`unsafe_allow_html`) | Opens an XSS path for the sake of polish, and fights the framework's rerun model. Not worth it. |
| Axios | `fetch` is sufficient; one fewer dependency. |

---

## 5. Repository layout

```text
timbre-pronunciation-studio/
  docs/
    PRD.md
    TRD.md
    App Flow.md
    UI-UX Brief.md
    Backend Schema.md
    Implementation Plan.md
  backend/
    app/
      main.py                  # app factory, error handlers, API routers
      config.py                # env loading, limits, defaults
      errors.py                # error taxonomy + HTTP mapping
      catalogue.py             # models and English voices
      deps.py                  # request-scoped accessors
      api/
        health.py
        options.py
        dictionaries.py
        rules.py
        transform.py
        synthesize.py
        audio.py
      core/
        pronunciation_rules.py # rule engine (pure functions)
        dictionary_store.py    # JSON CRUD
        gnani_tts.py           # TTS client
        audio_cache.py         # disk cache + sidecar, pay-once helper
        atomic.py              # unique temp file + locked replace
      models/
        schemas.py             # Pydantic models
    tests/
      conftest.py
      test_pronunciation_rules.py
      test_dictionary_store.py
      test_transform_api.py
      test_synthesize_api.py
      test_api_errors.py
      test_config.py
      test_gnani_tts.py
      test_audio_cache.py
      test_atomic.py
      test_try_respelling.py
      test_measure_limits.py
      fixtures/                # 6 dictionary files + export_valid.json
    requirements.txt
    .env.example
  streamlit_app/
    app.py                     # the whole UI: one entry point
    seed.py                    # first-run sample dictionary (App Flow §5)
    csv_io.py                  # CSV parse/export (no Streamlit, no network)
    tests/
      test_app_boot.py         # real app.py under AppTest: seed, stale clip
      test_app_rules.py        # rule editor: add, save, cancel, duplicates
      test_app_dictionaries.py # create/delete through the dialogs
      test_csv_io.py           # header aliases, errors, round trip
  scripts/
    smoke_test.py              # Milestone 2 live API check
    poc_matrix.py              # Milestone 3 before/after generator
    try_respelling.py          # Milestone 3 retry, user-authored respellings
    measure_limits.py          # Milestone 10: TQ4 latency and TQ5 ceiling probes
  data/
    dictionaries/              # runtime-created, gitignored
    audio/                     # runtime-created, gitignored
  .gitignore
  README.md
```

### 5.1 Layout notes

- `data/` is created at startup if missing. It is gitignored but **not** deleted between runs — dictionaries must survive restarts (FR-10).
- `scripts/` contains developer utilities that are **not** part of the shipped app. `smoke_test.py` must run with no FastAPI installed, so it depends only on `requests` and `python-dotenv`.
- `backend/app/core/` modules must not import from `backend/app/api/`. Dependencies point inward only. That is what lets the Streamlit UI import `core/` directly while the HTTP API stays intact.

---

## 6. Configuration

### 6.1 Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GNANI_API_KEY` | **Yes** | — | Sent as `X-API-Key-ID`. Never logged, never returned. |
| `GNANI_BASE_URL` | No | `https://api.vachana.ai` | Allows pointing at a test host |
| `GNANI_DEFAULT_MODEL` | No | `timbre-v3.0` | Preselected model |
| `GNANI_DEFAULT_VOICE` | No | `Lakshmi` | Preselected voice |
| `GNANI_LANGUAGE` | No | `en-IN` | Fixed in this release (FR-19) |
| `GNANI_SPEED` | No | `1.0` | Fixed; must be 0.85–1.15 or startup fails |
| `GNANI_TIMEOUT_SECONDS` | No | `60` | Per-request timeout; must be > 0 |
| `SCRIPT_WARN_CHARS` | No | `800` | Soft warning threshold |
| `SCRIPT_BLOCK_CHARS` | No | `2000` | Hard rejection threshold |
| `DATA_DIR` | No | `./data` | Dictionaries and audio |

### 6.2 Loading rules

1. `config.py` calls `load_dotenv()` once at import, then reads values into a frozen `Settings` object.
2. A missing `GNANI_API_KEY` raises a typed `ConfigurationError` at startup. The app must **not** start in a half-usable state (FR-31).
3. `.env.example` is committed with empty values and inline comments. `.env` is gitignored.
4. The key is never placed in a Pydantic model that is serialised to a response.

### 6.3 UI configuration

The Streamlit UI reads the same `backend/.env` through `backend/app/config.py`;
it has no configuration of its own and no separate `.env`. There is no build-time
variable because there is no build step.

`GNANI_API_KEY` must be **non-empty** for the process to start at all (§6.2), but
it is only *used* on a synthesis call. A placeholder value therefore runs
everything except generation — which is how the UI can be built and reviewed
without access to the owner's key or credits. `.env` is gitignored, so a fresh
clone has no `.env` until `.env.example` is copied.

No secret exists outside the Python process. If a secret is ever needed in browser
tooling, the design is wrong.

---

## 7. HTTP API contract

All endpoints are under `/api`. Request and response bodies are JSON except where noted. The exact field-level schema is owned by `docs/Backend Schema.md`; this section defines the endpoints and their semantics.

### 7.1 Endpoints

| Method | Path | Purpose | PRD ref |
|---|---|---|---|
| `GET` | `/api/health` | Liveness plus key-configured flag (boolean only, never the key) | FR-31 |
| `GET` | `/api/options` | Available models, their voices, fixed language and speed | FR-17, FR-18 |
| `GET` | `/api/dictionaries` | List dictionaries with rule counts | FR-08 |
| `POST` | `/api/dictionaries` | Create a dictionary | FR-08 |
| `PATCH` | `/api/dictionaries/{dictionary_id}` | Rename | FR-08 |
| `DELETE` | `/api/dictionaries/{dictionary_id}` | Delete dictionary and its rules | FR-08 |
| `GET` | `/api/dictionaries/{dictionary_id}/rules` | List rules | FR-09 |
| `POST` | `/api/dictionaries/{dictionary_id}/rules` | Create rule | FR-09 |
| `PATCH` | `/api/rules/{rule_id}` | Edit rule | FR-09 |
| `DELETE` | `/api/rules/{rule_id}` | Delete rule | FR-09 |
| `POST` | `/api/transform` | Apply rules; returns transformed text and match report | FR-03, FR-04, FR-07 |
| `POST` | `/api/synthesize` | Generate audio; returns metadata plus a playable URL | FR-23, FR-24 |
| `GET` | `/api/audio/{cache_key}` | Serve cached WAV bytes (a trailing `.wav` is accepted and stripped) | FR-24 |
| `GET` | `/api/dictionaries/{dictionary_id}/export` | **Not implemented** — stretch (FR-13); the format is specified in `Backend Schema` §16 | FR-13 |

### 7.2 `POST /api/transform`

Request:

```json
{
  "text": "Gnani AI makes voices.",
  "dictionary_id": "dict_01J8...",
  "rules": null
}
```

`rules` is an optional inline array that overrides the stored dictionary, used for live preview of unsaved edits (FR-07). If both are supplied, `rules` wins.

Response:

```json
{
  "original_text": "Gnani AI makes voices.",
  "transformed_text": "Gyaanee A I makes voices.",
  "changed": true,
  "char_count": 22,
  "limit": { "warn_at": 800, "block_at": 2000, "status": "ok" },
  "matches": [
    {
      "rule_id": "rule_01J8...",
      "source": "Gnani AI",
      "replacement": "Gyaanee A I",
      "count": 1
    },
    {
      "rule_id": "rule_01J8...",
      "source": "Timbre",
      "replacement": "Tamber",
      "count": 0
    }
  ]
}
```

`matches` includes zero-count rules so the UI can flag a mistyped source term (FR-04). This endpoint performs **no** network call and spends no credits.

### 7.3 `POST /api/synthesize`

Request:

```json
{
  "text": "Gyaanee A I makes voices.",
  "model": "timbre-v3.0",
  "voice": "Lakshmi",
  "language": "en-IN",
  "speed": 1.0
}
```

Response (`200`):

```json
{
  "cache_key": "a3f9c2...",
  "audio_url": "/api/audio/a3f9c2....wav",
  "cached": false,
  "bytes": 184320,
  "settings": {
    "model": "timbre-v3.0",
    "voice": "Lakshmi",
    "language": "en-IN",
    "speed": 1.0,
    "sample_rate": 48000,
    "num_channels": 1,
    "sample_width": 2,
    "container": "wav"
  }
}
```

`settings` is echoed so the UI can prove that a comparison pair used identical configuration (FR-21).

### 7.4 Status codes

| Code | Meaning | When |
|---|---|---|
| `200` | Success | — |
| `400` | Validation failure | Empty source term, duplicate term, script over `SCRIPT_BLOCK_CHARS`, reserved rule type |
| `401` | Upstream auth failure | Gnani returned 401 |
| `403` | Upstream permission or credits | Gnani returned 403 |
| `404` | Unknown dictionary, rule, or audio key | — |
| `409` | Name collision | Duplicate dictionary name |
| `422` | Malformed body | Pydantic rejection |
| `429` | Upstream rate limit | Gnani returned 429 |
| `502` | Upstream error | Gnani returned 500 or 503, or a 200 with an empty body |
| `503` | Upstream unreachable | `requests.ConnectionError` |
| `504` | Upstream timeout | `requests` timeout exceeded |

---

## 8. Rule engine specification

Module: `backend/app/core/pronunciation_rules.py`. Pure functions, no I/O, no network. This is the most-tested module in the project.

### 8.1 Data model

```python
@dataclass(frozen=True, slots=True)
class Rule:
    source: str
    replacement: str     # pronunciation-friendly text
    rule_id: str = ""    # the stored rule's id, for the match report
    created_at: str = "" # ISO 8601, used for deterministic ordering
```

The engine carries no `type` field: `phoneme` is rejected at the API boundary
before a rule ever reaches it (FR-12).

### 8.2 Algorithm

Single-pass regex substitution over the **original** string.

**Step 1 — Normalise and order.**
Sort rules by `(-len(source), created_at, id)`. Longest source first, so `Gnani AI` beats `Gnani` at the same position. Ties broken deterministically.

**Step 2 — Build one alternation pattern.**

```python
pattern = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(r.source) for r in ordered) + r")(?!\w)",
    re.IGNORECASE,
)
```

**Step 3 — Substitution via callback.**
A `dict[str, Rule]` keyed by `source.casefold()` maps each match back to its rule, returning `rule.replacement` verbatim. The replacement's casing is the author's choice; the match's casing is irrelevant.

**Step 4 — Report.**
Count matches per rule, including zeros, preserving rule order.

### 8.3 Behavioural guarantees

| Property | Guarantee | Mechanism |
|---|---|---|
| Whole-word only | `Ram` does not match inside `Ramachandran` | `(?<!\w)` / `(?!\w)` lookarounds |
| Punctuation boundaries | `Gnani's`, `(Gnani)`, `Gnani,` all match | Apostrophe, parenthesis and comma are non-word characters |
| Case-insensitive match | `gnani`, `GNANI`, `Gnani` all match one rule | `re.IGNORECASE` + `casefold()` lookup |
| Verbatim replacement | Replacement casing preserved exactly | Callback returns the stored string |
| Longest-first | `Gnani AI` wins over `Gnani` | Ordered alternation, longest first |
| No cascade | A replacement is never re-scanned in the same pass | `re.sub` scans only the input string |
| Determinism | Same input + same rules ⇒ identical output | Total ordering from step 1 |
| Phrase support | Multi-word sources match across spaces | Escaped source inserted literally |

### 8.4 Known limitations (must be documented, not hidden)

1. **Not idempotent when rules chain.** If rule A's replacement contains rule B's source, a second application changes the text again. Example: `A → B` and `B → C`; applying twice yields `C`. The engine reports the affected rule ids (`chained_rule_ids`) and `POST /api/transform` returns them as `RULE_CHAIN_DETECTED` warnings, so the UI can warn once it exists.
2. **Hyphenated compounds split.** `Gnani-AI` matches `Gnani` because `-` is not a word character. Accepted; documented.
3. **No morphological awareness.** `Gnani` does not match `Gnanis`. Accepted; the user adds a plural rule if needed.
4. **Unicode word boundaries.** `\w` is Unicode-aware in Python 3, so Devanagari sources behave correctly. Only English is in scope, but the engine does not break on Indic input.
5. **Case-insensitive matching is case-*preserving* only in the sense that the replacement is literal.** It cannot adapt casing to sentence position. Accepted.

### 8.5 Required unit tests

Every row of PRD §8.3 becomes a test, plus:

| Test | Expectation |
|---|---|
| Empty rule list | Output equals input; `changed` is `false` |
| Rule matching zero times | Reported with `count: 0`; output unchanged |
| Duplicate source terms | Rejected at the API layer, not silently deduplicated |
| Replacement containing `<` or `>` | Accepted by the engine, warned by the API layer (FR-06) |
| Chained rules | Second application changes output; warning condition detected |
| Unicode source | Devanagari source matches Devanagari text |
| 500-character script with 50 rules | Completes under 50 ms |
| Determinism | Two runs on identical input produce byte-identical output |

---

## 9. TTS client

Module: `backend/app/core/gnani_tts.py`.

### 9.1 Request construction

```python
requests.post(
    f"{settings.base_url}/api/v1/tts/inference",
    headers={
        "Content-Type": "application/json",
        "X-API-Key-ID": settings.api_key,
    },
    json={
        "text": text,
        "model": model,
        "voice": voice,
        "language": language,
        "speed": speed,
        "audio_config": {
            "sample_rate": 48000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    },
    timeout=settings.timeout_seconds,
)
```

### 9.2 Response handling

| Condition | Action |
|---|---|
| `200` with non-empty body | Return bytes |
| `200` with empty body | Raise `UpstreamError` ("empty audio response") |
| `400` | Parse the upstream reason (`error.{type,message}` or the flat `{status_code,message}` shape, see Backend Schema §11.4); raise `UpstreamBadRequest` |
| `401` | Raise `UpstreamAuthError` |
| `403` | Raise `UpstreamForbiddenError` (mentions key, permission or credits) |
| `429` | Raise `UpstreamRateLimitError` |
| `500`, `503` | Raise `UpstreamError` with the returned message if parseable |
| `requests.Timeout` | Raise `UpstreamTimeoutError` |
| `requests.ConnectionError` | Raise `UpstreamUnreachableError` |

### 9.3 Deliberate omissions

- **No automatic retry.** A retry risks a duplicate charge if the first call succeeded but the response was lost. The user re-clicks; the UI keeps the request state so re-clicking is one action.
- **No streaming.** SSE and WebSocket add complexity with no MVP benefit; REST returns full audio in one response.
- **No SDK.** See §4.1.
- **No client-side text truncation.** Over-limit text is rejected before the call, never silently cut.

### 9.4 Logging discipline

Log method, path, model, voice, character count, status code and elapsed milliseconds. **Never** log the key, the header value, or the script text. On error, log the upstream `error.type` and `message`.

---

## 10. Persistence

Module: `backend/app/core/dictionary_store.py`. Field-level schema is defined in `docs/Backend Schema.md`.

### 10.1 Strategy

- One JSON file per dictionary: `data/dictionaries/{dictionary_id}.json`.
- Full-file read/write on every mutation. Dictionaries are small (tens of rules); atomicity matters more than throughput.
- Write via a temporary file in the same directory, then `os.replace()`. This prevents a truncated file if the process dies mid-write.
- An in-process `threading.Lock` serialises writes. The Streamlit UI issues single-user traffic, but the FastAPI surface may serve concurrent requests.

### 10.2 Identifiers

- `dictionary_id` and `rule_id` are UUIDv4 strings with prefixes (`dict_`, `rule_`).
- The dictionary **name** is user-facing and must be unique case-insensitively; the ID is the stable key, so renaming never breaks references.

### 10.3 Validation at the boundary

| Check | Where | Failure |
|---|---|---|
| Non-empty name, ≤80 chars | API layer | `400` |
| Unique name (case-insensitive) | Store | `409` |
| Non-empty source and replacement | API layer | `400` |
| `type == "alias"` | API layer | `400` for `phoneme` until native support is verified (FR-12) |
| Duplicate `source` within dictionary (case-insensitive) | API layer | `400` |
| Replacement contains `<` or `>` | Transform layer | `200` plus `warnings[]` on `/api/transform` (FR-06). Rule create and edit accept the value and return the rule alone; the UI warns at editing time |

### 10.4 Deletion

Deleting a dictionary deletes its file. Audio cache entries are **not** deleted, because they are content-addressed and may be referenced by another dictionary.

---

## 11. Audio handling and caching

Module: `backend/app/core/audio_cache.py`.

### 11.1 Cache key

```text
cache_key = sha256(f"{text}\x1f{model}\x1f{voice}\x1f{language}\x1f{speed}\x1f{audio_config_json}")
```

Including every setting guarantees that changing a voice produces a different key — a mis-keyed cache would silently break the comparison and is the single most damaging caching bug possible here.

### 11.2 Disk cache

| Storage | Lifetime | Purpose |
|---|---|---|
| `data/audio/{cache_key}.wav` | Until deleted manually | Avoids re-spending credits on repeated plays (FR-28); lets the user inspect and archive output (FR-24) |
| `data/audio/{cache_key}.json` | Same | Sidecar: the text, settings and upstream status the clip was generated with |

There is no in-memory tier. The disk file is the cache, so a restart and a second
process both see the same hits, and memory cannot grow with the number of clips.
Reads are one `read_bytes()`; the files are small enough at this scale, and a
process-lifetime copy would hide a stale file after a manual cleanup.

`AudioCache.get_or_synthesize()` is the one pay-once path: it computes the key,
returns a hit from disk, or synthesises once under a process lock and writes the
WAV and its sidecar. The API route and the Streamlit panel both call it, so the key
and sidecar shape cannot drift. If the cache write fails after a paid call, the
audio is still returned — the credit has already been spent.

### 11.3 Cleanup

No automatic eviction in the MVP. A `data/audio/` directory of a few dozen WAVs is harmless. The README documents manual cleanup. If disk growth becomes a problem, add an LRU cap after freeze — not before.

### 11.4 Serving

`GET /api/audio/{cache_key}` streams the file with `Content-Type: audio/wav` and `Accept-Ranges: bytes` so the browser's audio element can seek. The `cache_key` is validated against `^[a-f0-9]{64}$` before touching the filesystem to prevent path traversal.

---

## 12. UI architecture (Streamlit)

**Decided 21 October 2026.** The UI is built in Streamlit by the teammate. This
section replaces the earlier React plan, which is recorded in §13 as rejected.

### 12.1 Structure

One page, sidebar plus main column. No router, no build step, no JavaScript.

```text
streamlit_app/app.py
 ├─ sidebar   dictionaries (selector, +, ⋮ rename/delete), voice,
 │            fixed language and speed
 ├─ hero      title and the one-line promise
 ├─ script    textarea, character counter, limit state
 ├─ rules     rule table: add, edit, validate, save, cancel, delete
 ├─ preview   original vs "Sent to Timbre", substituted spans tinted
 └─ audio     Generate comparison, two waveform players, cached/fresh badge
```

The panels live in `app.py` rather than a `ui/` package. `AppTest` drives the
real page, so the tests exercise the same code that ships; there is no second
copy of the layout to keep in step.

Two helpers sit beside it. `seed.py` creates the first-run sample dictionary
(`App Flow` §5). `csv_io.py` parses and exports CSV and imports neither
Streamlit nor `app.*`, so it is tested directly and cannot touch the network.

### 12.2 State model

| State | Owner | Notes |
|---|---|---|
| `active_id` | `st.session_state` | **Not persisted across a browser refresh** — see §12.6 |
| `draft_rows`, `drafts_for`, `draft_seq` | `st.session_state` | Editable copy of the stored rules until Save; `drafts_for` tracks which dictionary they belong to |
| `script_text` | `st.session_state` | The transform runs on this value |
| `model_pick`, `voice_pick` | `st.session_state` | Applied settings; drafts hold the pending choice until Apply |
| `audio_result` | `st.session_state` | `{sig, original, adjusted, *_cached}`; dropped when `sig` no longer matches |
| `voice_preview` | `st.session_state` | One cached preview clip per voice |
| `seeded` | `st.session_state` | First run only; retried if seeding failed |
| `seed_error` | `st.session_state` | Shown in the sidebar, never swallowed |
| `pending_new`, `pending_import`, `pending_delete` | `st.session_state` | Re-open a dialog after the rerun that closed it |

### 12.3 Interaction rules

1. **Transformation is local and free.** Every run recomputes the transform from
   the current script and rules through `core.pronunciation_rules`. No credits.
   Streamlit re-runs the script on every widget change, so no debounce is needed.
2. **Synthesis is explicit only.** The **Generate** button is the sole path to
   `TimbreClient.synthesize` (FR-23). Streamlit buttons are single-shot, so there
   is no duplicate-submit path to guard.
3. **Settings are frozen per comparison.** Changing model or voice clears
   `audio_result`, so a stale pair can never be mistaken for a valid comparison
   (FR-21).
4. **No-op guard.** If the transform did not change the text, Generate is disabled
   with "No rules matched — nothing to compare" (FR-27).
5. **Errors are visible and actionable.** Catch `AppError`, show `exc.message` and
   its status code and error type from `core.errors`; upstream detail is already
   attached (FR-26).
6. **Sidebar mutations run in callbacks, never inline with `st.rerun()`.** A
   callback runs before the page is drawn, so the create/rename/delete result is
   visible in the same pass. Calling `st.rerun()` from a sidebar form handler
   aborts the run before the main-column editor is rendered, and Streamlit then
   discards the `script` widget's state — the user's text disappears. Found and
   fixed on 26 October 2026 while building the editor.
7. **Rules are edited as drafts; the preview never waits for a save.** Each row is
   a pair of text inputs and a delete button. Nothing is written until Save. The
   preview transforms the draft rows, so an unsaved edit shows its effect at once
   (Flow 3). Save validates locally, writes the whole table in one `set_rules`
   call, and reloads from disk so a partial failure is visible as what actually
   persisted. The widget key carries a sequence number so Save/Cancel replace the
   inputs' own state instead of leaving discarded cells behind; the session drops
   the previous sequence's key on the next run so dead entries do not accumulate.
8. **Add appends to the draft, never the store.** The two-field Add rule form
   validates the term first (empty, over the length limit, duplicate) and only
   then appends a row. The preview and the rule count update on that same rerun.
9. **Audio is generated only inside the click branch.** No load, script change or
   rule change can reach `TimbreClient.synthesize`. The click freezes model,
   voice, language and speed, then calls original and transformed **sequentially**
   through `AudioCache.get_or_synthesize()`. A failure shows `exc.message` and
   draws no pair; the half that succeeded is already on disk, so pressing
   **Generate comparison** again normally costs nothing for it.
10. **The audio panel is cache-first, through the shared helper.**
   `AudioCache.get_or_synthesize()` is the same call `api/synthesize.py` makes,
   so the cache key and sidecar shape cannot drift between the API and the UI. An
   identical request — including a second Generate — is served from disk with no
   upstream call (FR-28).
11. **A clip is shown only for the draft it was generated from.** The stored
    signature is `(text, transformed_text, model.id, voice.id)`. On every run the
    panel compares it with the current values and drops the result when they
    differ, so no player can be labelled with a pair it was not generated from
    (FR-21). Both blocks then read "Generate the comparison to hear this clip."

### 12.4 What the UI calls

The UI imports the same modules the API uses. It does **not** call the HTTP API,
which removes CORS, ports and a second process from the demo:

```python
from app.core.pronunciation_rules import Rule, apply_rules
from app.core.dictionary_store import DictionaryStore
from app.core.gnani_tts import TimbreClient
from app.core.audio_cache import AudioCache
from app.config import load_settings
```

`backend/app/api/` remains the tested HTTP contract (`Backend Schema`). If the UI
ever needs to run against it instead, nothing in `backend/` changes.

The one piece the UI used to repeat is now shared: the audio panel calls
`AudioCache.get_or_synthesize()`, the same helper `api/synthesize.py` uses, so the
cache key and sidecar shape are identical by construction and a replay costs
nothing. The model, voice, language and speed used are visible in the sidebar.

### 12.5 Styling

The "Sand · warm" identity from `UI-UX Brief` is applied as one `<style>` block
through `st.markdown(..., unsafe_allow_html=True)`: cream page, white cards,
brown accents. Streamlit themes the page, widgets and text; the CSS only paints
surfaces the theme has no token for. A second block is appended when
`theme.base` is dark, so the same layout stays legible in dark mode.

Panels are `st.container(border=True)`. The rule table is one text-input row per
rule, which gives per-row delete buttons without a data editor (§12.3 rule 7).
Substituted spans are tinted with `<mark>` in the preview only (`UI-UX Brief`
§8.7). Each generated clip is drawn by a small waveform player: peaks are
computed from the WAV, served through Streamlit's media manager, and played in a
same-origin iframe. If the media URL cannot be resolved, the player falls back to
the native `st.audio` control, so a clip is never silently missing
(`docs/LIMITATIONS.md` 26).

### 12.6 Persistence difference (accepted)

The React plan stored the active dictionary and the last script in `localStorage`.
Streamlit has no browser storage, so a page refresh returns to the first
dictionary and an empty editor. Dictionaries themselves persist on disk and
survive restarts (FR-10), which is what US-07 actually requires. This is recorded
in `docs/LIMITATIONS.md`.

---

## 13. Rejected alternative — React SPA

**Rejected 21 October 2026**, before any React code existed. Recorded here so the
decision is not silently reopened, and so the trade-off is visible in the
submission.

| Reason | Detail |
|---|---|
| Two toolchains | Node, Vite, TypeScript, `npm install` and a build step to demo a local single-user tool |
| Two processes | A dev proxy and a CORS configuration, both of which can fail live |
| Skill match | The teammate's time is better spent on the flow than on scaffolding |
| No capability lost | Every MVP requirement is reachable in Streamlit; only visual polish is lost (`UI-UX Brief` §16.1) |

**Cost if it were revived:** the backend is unchanged, so it is the 18–22 h UI
build against the existing API contract. Nothing in `core/` or `api/` would move.
That reversibility is the only reason this is a cheap rejection to record.

---

## 14. Non-functional requirements

| ID | Requirement | Target | Verified by |
|---|---|---|---|
| NFR-01 | Synthesis round trip for ≤800 characters | ≤ 10 s p95 | **PASS on 22 Oct 2026** (weak estimate): 5 distinct scripts of 787–799 characters → median 6,157 ms, slowest 6,905 ms, 4.4–4.8 MB each. With 5 samples the nearest-rank p95 *is* the slowest sample, so this bounds the true p95 from below. Method: `scripts/measure_limits.py`; raw data: `data/limits_results.json` (gitignored). Not a further PASS: a 2,000-character request also finished in 9,197 ms, but NFR-01's scope is ≤800 characters, and latency does not rise monotonically with length (2,000 characters was 1.8 s *faster* than 1,897) |
| NFR-02 | Transformation latency, 50 rules, 2,000-character script | ≤ 50 ms | Unit test |
| NFR-03 | Backend cold start | ≤ 5 s | Manual |
| NFR-04 | ~~Frontend production bundle ≤ 500 KB gzipped~~ **Not applicable** — Streamlit ships no bundle and no build step (§12) | — | — |
| NFR-05 | No secret in any response body, log line, or committed file | Absolute | Manual audit + `grep` of the repository |
| NFR-06 | Path traversal impossible on `/api/audio/{cache_key}` | Absolute | Regex validation + test |
| NFR-07 | App starts with a clear error and exits if the key is missing | Absolute | Test |
| NFR-08 | Works offline except for synthesis | Transformation, editing and playback of cached audio function without network | Manual |
| NFR-09 | Supported browsers | Latest Chrome and Edge on Windows | Manual |
| NFR-10 | Keyboard navigable | All controls reachable by Tab; visible focus ring | **PASS** — owner keyboard-only walkthrough of the full workflow, reported working before the freeze. Manual, no automated test |

---

## 15. Testing strategy

### 15.1 Scope

| Layer | Approach | Rationale |
|---|---|---|
| Rule engine | pytest, exhaustive | Correctness core; cheap to test; high defect density |
| Dictionary store | pytest with a temp directory | Persistence and validation defects are silent and destructive |
| API contract | pytest with FastAPI `TestClient`, TTS client mocked | Verifies status codes without spending credits |
| TTS client | pytest with `requests` mocked; one live test in `scripts/` | Deterministic unit tests plus one real check |
| Frontend | Manual walkthrough checklist | Time budget; correctness does not live here |

### 15.2 Mandatory test cases

| File | Cases |
|---|---|
| `test_pronunciation_rules.py` | All PRD §8.3 examples; empty rules; zero-match reporting; chained-rule detection; Unicode source; 50-rule performance; determinism |
| `test_dictionary_store.py` | Create, rename, delete; duplicate name rejection; atomic write; corrupt and future-version files skipped; reload after restart |
| `test_transform_api.py` | 200 happy path; 400 on duplicate or blank inline source/replacement; 400 over block limit (whitespace excluded); warn status at 800; 404 unknown dictionary; inline rules override the stored dictionary |
| `test_synthesize_api.py` | Voice/model mismatch; unsupported language; speed range; cache hit (`cached: true`) with no second upstream call; audio served at `/api/audio/{key}.wav`; a failed cache write still returns the paid audio |
| `test_api_errors.py` | 422 envelope for a malformed body; 404 envelope for an unknown path |
| `test_config.py` | Missing key raises at startup; defaults applied correctly; speed outside 0.85–1.15 rejected; non-positive timeout rejected |
| `test_gnani_tts.py` | Status-to-error mapping; both upstream error-body shapes; empty 200 body; timeout and connection failure |
| `test_audio_cache.py` | Every one of the six key inputs changes the key; duration from the PCM payload, not the declared frame count; the shared helper pays once and then reads disk; a failed cache write keeps the paid audio; two threads asking for one clip pay once |
| `test_atomic.py` | Six concurrent writes to one target all land, whole, with no temp file left behind |
| `test_try_respelling.py` | Manifest loading, sheet rendering, credit guard, dry-run safety, and reuse of audio the shared cache already holds |
| `test_smoke_test.py` | The script refuses to make its first paid call until the human confirms |
| `test_measure_limits.py` | TQ4 samples stay within 800 characters and are distinct (a cached sample would time the cache, not the network); ceiling probes straddle the 2,000-character block; dry run constructs no client and writes no result; `--probe` narrows the plan to one label and rejects an unknown label; **a free rerun keeps the timings already on file instead of blanking them**, records made under other settings or for removed labels are dropped, character counts stay aligned with the timings, and a failed cache write does not lose a paid measurement |

All twelve backend files plus `conftest.py` exist; the backend suite is **147
tests**, green. The Streamlit UI adds **37** in `streamlit_app/tests/`, so the
documented command in §16.4 runs **184**.

### 15.3 Manual walkthrough (release checklist)

1. Fresh start with `.env` present → app loads, dictionary list populated.
2. Create dictionary, add three rules, refresh browser → rules persist.
3. Paste a script → preview updates without network calls to Gnani.
4. Generate → both players work; the model and voice in the sidebar match the pair.
5. Change voice → players clear; regenerate produces different audio.
6. Restart backend → dictionaries still present.
7. Remove the key from `.env` → app fails with a clear message.
8. `grep` the repository for the key string → absent (there is no `dist/` to inspect; nothing is built).

### 15.4 Live API checks (not pytest)

- `scripts/smoke_test.py` — one call per model, saves WAVs, prints status and byte count.
- `scripts/poc_matrix.py` — the Milestone 3 before/after generator, holding settings constant.
- `scripts/try_respelling.py` — the Milestone 3 retry. Same settings, same rule engine, but the respelling comes from the user. Caches by text so a sentence is never paid for twice, and reuses a round-1 original when the sentence and settings are unchanged. `interactive` prompts for a respelling per term and rebuilds the listening sheet `data/audio/try/listen.html` after each one, so the judgement is made in the browser rather than in an external media player; `verdict --verdict "Term=closer|note"` records the verdict and refreshes the sheet.
- `POST /api/synthesize` with a text that is already in `data/audio/` — a cache hit, so it spends nothing. **Verified 22 Oct 2026** on a 787-character script: `cached: true`, the returned key matched the sidecar, and `/api/audio/{key}.wav` served the same 4,746,284 bytes. This is the only check that exercises the HTTP layer; the scripts above call the client directly, and a miss would have returned 401 rather than spending a credit because the server was started with a placeholder key.

These are run manually because they spend credits. They must never be part of an automated test run.

---

## 16. Build, run and deploy

### 16.1 First-time setup (Windows, bash / Git Bash)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # then paste the key into backend/.env
```

The UI's one dependency is pinned in
`backend/requirements.txt` (`streamlit>=1.40`), so a fresh clone gets it from the
install command above and no manual step is needed. No Node, no `npm`, no build
step.

### 16.2 Development

**Canonical command — run from the project root:**

```bash
.venv/Scripts/python.exe -m streamlit run streamlit_app/app.py
```

This form is cwd-independent, so it works from a fresh terminal, an IDE run
button, or the demo recording. It requires the bootstrap block below at the top
of `streamlit_app/app.py`, before any `from app...` import, because Streamlit
does not reliably put `backend/` on `sys.path`:

```python
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parents[1] / "backend"), str(_HERE.parent)]
```

Two directories are added, not one. `backend/` makes `app.*` importable; the
script's own directory makes `seed` and `csv_io` importable. `streamlit run`
usually adds the latter itself, but `streamlit.testing.v1.AppTest` does not, and
the app has to behave identically under both.

Streamlit prints the local URL (default `http://localhost:8501`).

**Restart the server after editing any file under `streamlit_app/`.** Streamlit
1.60 in this venv has no source-module reloader: a new browser session re-executes
`app.py` from disk, but modules already imported by the process (`seed`,
`csv_io`) stay cached in `sys.modules`. A browser refresh can therefore pair new
`app.py` code with an old helper. Verified 25 October 2026 by reproducing the
error against a cached module; after the restart every check passes.

Fallback, if the bootstrap is ever removed: `cd backend` and then
`../.venv/Scripts/python.exe -m streamlit run ../streamlit_app/app.py`, which
puts `app` on the import path via the working directory. Only one of the two
should be documented in the README; the root form is preferred (risk T4).

The HTTP API is optional and used for `/docs` and its own tests:

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --reload --port 8000
```

### 16.3 Demo / release

The same single command as §16.2. One process, no build, no proxy, no CORS.

### 16.4 Tests

```bash
.venv/Scripts/python.exe -m pytest backend streamlit_app/tests -q
```

### 16.5 Deployment

None. Local execution only. The submission requires a demo video and public post, not a hosted URL.

---

## 17. Security

| Concern | Control |
|---|---|
| Key exposure in the browser | Key lives in the local Python process (FastAPI or Streamlit); the browser never receives it |
| Key in version control | `.env` gitignored; `.env.example` contains empty values only |
| Key in logs | Logging excludes headers and text; audited in NFR-05 |
| Key in error messages | Upstream error text is forwarded, but headers are never echoed |
| Path traversal | `cache_key` validated against a 64-hex-character regex |
| Arbitrary file read | No endpoint accepts a path; all file access is derived from validated IDs |
| XSS | Streamlit renders user text as text; `unsafe_allow_html` stays off, so scripts and replacements can never become HTML |
| Injection | No SQL, no shell execution, no `eval` |
| CORS | Not enabled: the app serves only `/api/*` and the UI calls `core/` in-process, so no browser origin needs it |
| Untrusted upstream data | Response bodies parsed defensively; non-JSON error bodies do not crash the client |
| Privacy | No telemetry; the only outbound traffic is the TTS request. Streamlit gathers usage statistics **by default**, so `.streamlit/config.toml` sets `browser.gatherUsageStats = false` — without it the demo would report usage to Streamlit and breach FR-34 |

---

## 18. Risks specific to this design

| # | Risk | Mitigation |
|---|---|---|
| T1 | Normalisation layer rewrites authored respellings | Preview shows the exact text sent; POC tests each term's survival (PRD R1) |
| T2 | UI build overruns | Streamlit decided 21 Oct (§12); 5–7 h, with the visual scope in `UI-UX Brief` §16.1 already cut |
| T3 | Cache key omits a setting, silently corrupting comparisons | Key includes all six inputs; unit test asserts a voice change yields a different key |
| T4 | Windows path/quoting issues in setup | Commands verified on Windows. The Streamlit entry point bootstraps `sys.path` itself (§16.2), so no `cd` and no `PYTHONPATH` is required |
| T5 | Concurrent writes corrupt a dictionary file | `threading.Lock` plus `os.replace()` atomic write |
| T6 | Character limit is unverified against the real API | **Retired 22 Oct 2026.** 2,000 characters is accepted (9,197 ms), 2,100 is rejected in 133 ms as a generic 502. Warn at 800, block at 2,000 — the block is now a verified ceiling, not an assumption (`TRD` §20 TQ5b, `LIMITATIONS` — Measured limits) |
| T7 | Teammate's availability drops | The UI is a thin Streamlit layer over tested `core/` modules; one person can rebuild it in 5–7 h |

---

## 19. Requirement traceability

| PRD requirement | Implemented in |
|---|---|
| FR-01, FR-02, FR-03, FR-04, FR-07 | `POST /api/transform`; `streamlit_app/app.py` (editor and preview) |
| FR-05 | `config.py` limits; enforced in transform and synthesize |
| FR-06 | API-layer warning on `<` / `>` in replacement |
| FR-08, FR-09, FR-10, FR-11, FR-12 | `dictionary_store.py`, `streamlit_app/app.py` (dictionaries and rule editor) |
| FR-13, FR-14, FR-15 | Stretch — endpoint reserved, not implemented before freeze |
| FR-17, FR-18, FR-19, FR-20, FR-21 | `GET /api/options`, `streamlit_app/app.py` (voice panel and signature check), settings echo in synthesize response |
| FR-23, FR-24, FR-25, FR-26, FR-27 | `synthesize.py`, `audio_cache.py`, `streamlit_app/app.py` (Generate and players), `st.error` on `AppError` |
| FR-28 | `audio_cache.py` disk cache via `get_or_synthesize` |
| FR-29 | Stretch — not implemented |
| FR-30, FR-31, FR-32, FR-33, FR-34 | `config.py`, `.gitignore`, §17 |
| NFR-01…NFR-10 | §14 |

---

## 20. Open technical questions

| # | Question | Resolves by | Owner |
|---|---|---|---|
| TQ1 | Is `timbre-v2.5` reachable with the participant's key? | **Resolved 20 Oct 2026: yes.** HTTP 200, 276,524 bytes | You |
| TQ2 | Does normalisation alter authored respellings? | **Resolved 21 Oct 2026:** the respelling is spoken as spelled in 7 of 8 pairs, partly in 1, never not | You |
| TQ3 | Does any SSML/phoneme mechanism work on this endpoint? | **Resolved 22 Oct 2026: no.** 200 returned, but the tag is stripped, not spoken | You |
| TQ4 | Actual p95 latency for 800 characters? | **Resolved 22 Oct 2026: PASS, with a caveat.** 5 distinct scripts of 787–799 characters at `timbre-v3.0`/`Lakshmi`/`en-IN`/`1.0`: 4,377 / 4,744 / 6,157 / 6,900 / 6,905 ms → median 6,157 ms, slowest-of-five 6,905 ms, inside the 10 s target. Nearest-rank p95 with n=5 is the slowest sample, so this is a lower bound on the true p95, not a population figure. Response size 4.4–4.8 MB per script. Method: `scripts/measure_limits.py` | You |
| TQ5 | Does the API enforce a length ceiling below 2,000 characters? | **Resolved 22 Oct 2026: no — the ceiling sits between 2,000 and 2,100.** 1,897 characters → HTTP 200, 10,970 ms, 11.2 MB. 2,000 characters → HTTP 200, 9,197 ms, 12.0 MB. 2,100 characters → failure in **133 ms**, surfaced by the client as `UPSTREAM_ERROR` (502). The speed of the rejection implies a gateway/size guard, not a synthesis timeout, and the upstream returns no usable length message. The 2,001–2,099 band is untested but unreachable through the app, so the exact threshold does not affect shipped behaviour | You |
| TQ5b | Does exactly 2,000 characters — the largest script the app will send — succeed? | **Resolved 22 Oct 2026: yes.** 2,000 characters → HTTP 200 in 9,197 ms, 11,965,484 bytes. The local block at 2,000 (`SCRIPT_BLOCK_CHARS`) is therefore correct rather than merely cautious: the maximum script the app allows is one the API accepts, and 2,001 is where the opaque 502 would begin. No code change needed | You |
| TQ6 | Does `streamlit run` launched from `backend/` import `app.core` cleanly on Windows? | **Resolved in practice 30 Oct 2026 from the repository root.** The §16.2 command starts the app, imports `app.core` and runs the full workflow. The `backend/`-cwd fallback is not exercised, and the bootstrap makes the question independent of cwd | Teammate |

---

## 21. Approval

Approved when both builders confirm:

- [ ] The architecture in §3 is accepted: Streamlit in-process over `core/`, with the HTTP API kept as the tested contract.
- [ ] The rule engine specification in §8 is accepted as the correctness contract.
- [ ] The no-retry decision in §9.3 is accepted, understanding the credit rationale.
- [ ] The repository layout in §5 matches the agreed ownership split.
- [ ] NFR-05 (no secret exposure) is accepted as absolute, not best-effort.

Changes to architecture after approval require an update to this document before implementation, not after.
