# Agent rules for this repository

These rules are binding for **any** AI assistant, whatever model or tool is in use.
They exist because an assistant once made live API calls on its own and spent the
owner's Gnani programme credits. Read this file before running anything.

This is the **only** AI-instruction file the repository commits. Tool-specific stubs
(`CLAUDE.md`, `GEMINI.md`, `.cursor/`, `.kilo/`, `.freebuff/`) are gitignored and
exist only on the owner's machine; each one merely points here, so nothing is lost
in a clone. If a rule needs to apply to a new tool, add it to this file — do not
create another stub and commit it.

---

## 1. Never spend Gnani credits without explicit approval in the current conversation

The owner's credits are a hard, finite budget. Spending them without permission is
the single worst mistake available in this repository.

**These actions spend credits (money):**

| Action | Cost |
|---|---|
| `scripts/poc_matrix.py` without `--dry-run` | 16 calls |
| `scripts/smoke_test.py` without `--confirm-spend` | 4 calls (3 with `--skip-latency`) |
| `scripts/try_respelling.py original` / `adjusted` / `interactive` without `--dry-run` | 1 call per file not already cached |
| `scripts/measure_limits.py` without `--dry-run` | 8 calls (fewer if the audio is cached) |
| `POST /api/synthesize` against a real key | 1 call (0 if the audio is cached) |
| Any `curl` / `requests` / SDK call to `https://api.vachana.ai` | 1 call per request |
| Re-running a script "to check it still works" | 0 if the audio is already cached, otherwise the full cost again |

**Rules:**

1. **Default to `--dry-run`.** It computes the transform, prints the plan, and makes
   zero calls. It is the correct way to verify this project's tooling.
2. **Never pass `--confirm-spend`** (or answer the "type spend" prompt) unless the
   owner has said yes to that specific spend in the current conversation.
3. **Never bypass the guard.** Do not pipe input into it, do not set environment
   variables, do not edit the guard out, do not call the upstream API directly to
   route around it. A guard that fires is an answer, not an obstacle.
4. **Tests must never touch the network.** Use the stubs in `backend/tests/conftest.py`
   (`fake_tts`) and the `fake_client` fixture in
   `backend/tests/test_try_respelling.py`. If you need new coverage, stub it.
5. **If a task seems to need a paid call, stop and ask first.** State the maximum
   number of calls, what each one is for, and whether anything is already cached.
   Wait for a clear yes. "It's only one call" is not an exception.
6. **Reusing cached audio is free.** Check `data/try_results.json` and
   `data/audio/` before assuming a call is needed; the script's estimate already
   does this.

## 2. Never expose or modify secrets

- `backend/.env` holds the API key. Never read it aloud, print it, copy it, commit
  it, or put it in a command line, a log, a test, or a document.
- `backend/.env.example` is the only place for key *names*, never values.
- If a key appears in output, stop and tell the owner to rotate it.

## 3. Do not weaken checks to make them pass

- Do not delete or skip a failing test, loosen an assertion, or add a suppression
  to get a green run.
- If a test fails, fix the cause. If the test itself is wrong, say so explicitly and
  explain why before changing it.
- Preserve the exit status of the command you are testing; a successful output
  filter is not a passing test.

## 4. Keep the documentation true

- The project's honesty about its limitations (`docs/LIMITATIONS.md`) is a product
  requirement, not decoration. Never inflate a claim, and never present an unverified
  listening judgement as measured evidence.
- Update docs in the same change as the code they describe.

## 5. Scope

- No paid services beyond Gnani. No network deployment. Local only.
- Do not commit, push, or publish unless the owner asks.
