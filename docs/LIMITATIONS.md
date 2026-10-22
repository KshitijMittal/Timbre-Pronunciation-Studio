# Known limitations

This product is an **application-side workaround**, not native phoneme control.
It rewrites the text sent to Timbre and keeps the original script for display.
Everything below is a consequence of that design and is accepted, not hidden.

## Rule matching

1. **Not idempotent when rules chain.** If rule A's replacement contains rule B's
   source, applying the same dictionary twice changes the text again
   (`A → B`, `B → C`; twice yields `C`). The transform response emits
   `RULE_CHAIN_DETECTED` so the UI can warn, but nothing prevents it.
2. **Hyphenated compounds split.** `Gnani-AI` matches the `Gnani` rule because
   `-` is not a word character. Add a rule for the full compound if needed.
3. **No morphological awareness.** `Gnani` does not match `Gnanis`. Add a plural
   rule explicitly; the engine will not guess.
4. **Whole-word only.** `Ram` never matches inside `Ramachandran`. That is the
   intended protection, but it also means no prefix or infix matching.
5. **No regex, substring or case-sensitive modes.** Source terms are literal.
6. **Replacement casing is literal.** Case-insensitive matching still inserts the
   author's exact replacement, so it cannot adapt to sentence position.
7. **Unicode boundaries are `\w`-based.** Indic scripts work, but combining marks
   and zero-width joiners can behave differently from Latin text.
8. **Duplicate sources are rejected case-insensitively.** `Timbre` and `TIMBRE`
   cannot coexist in one dictionary; the API returns a validation error.

## Model behaviour

9. **Timbre's text normalisation may rewrite authored respellings.** Respellings
   are best authored as plain lowercase words; inline markup is stripped before
   synthesis, which is why replacements containing `<` or `>` raise
   `REPLACEMENT_CONTAINS_MARKUP`.
10. **Pronunciation quality is judged by listening.** No numeric score is shown,
    and no ASR transcript is treated as proof of pronunciation.
11. **The 8-term POC does not generalise.** An 8-of-8 result describes those
    terms with that model and voice, not all names, voices or languages. The
    verdicts were also one listener's, on full sentences, in one session.
12. **English only (`en-IN`).** Language and speed are fixed in this release.
    Requests for another language are rejected rather than silently coerced.

## Storage and operation

13. **Local only, single user, no authentication.** Anyone who can reach the port
    can use the API. Do not expose it on a network interface.
14. **Dictionaries are plain JSON files** in `data/dictionaries/`, one per
    dictionary. A corrupt file is skipped with a warning instead of blocking
    startup; it is not repaired automatically.
15. **No undo.** Deleting a dictionary or rule is permanent.
16. **Audio is never evicted.** `data/audio/` grows until cleaned manually.
    Generated WAVs and their `.json` sidecars contain the script text; they are
    local artefacts and are gitignored.
17. **Format version 1 only.** A file with a higher `schema_version` is refused
    rather than guessed at, so a downgrade cannot silently lose data.
18. **No export/import yet.** Reserved as stretch work (FR-13, FR-14); the
    plan already schedules them as the first cut at Checkpoint 2
    (`Implementation Plan` §8.2), so nothing in the MVP depends on them.
19. **No batch rendering** across a whole dictionary.
20. **Upstream WAV headers use placeholder chunk sizes.** Timbre writes
    `0xFFFFFFFF` for the RIFF and `data` sizes, so `duration_seconds` is derived
    from the real PCM payload. Files are 48 kHz mono 16-bit, about 96 KB per
    second; a strict player that trusts the header may not seek correctly.
21. **The seed was judged once, by one listener.** The three seed rules in
    `docs/App Flow.md` §5 are Gate B winners — each judged `closer` against its
    original with settings held constant. That is a viability check (8 terms,
    `timbre-v3.0`, `Lakshmi`, English, one session), not an accuracy rate, and no
    percentage is claimed from it. Coimbatore improved only partly and is
    therefore not seeded. The per-term record is
    `docs/evidence/gate-b-try_results.json`; the audio is local only.

## UI (Streamlit)

22. **The active dictionary and the last script are not remembered.** They live in
    Streamlit's session state, so a browser refresh or restart returns to the first
    dictionary and an empty editor. The dictionaries themselves are on disk and
    survive (US-07). The earlier React plan stored this in `localStorage`; the
    Streamlit decision trades that away (`TRD` §12.6).
23. **Visual polish is reduced.** No dark mode, no mobile rule-card layout, no diff
    tinting inside the transformed pane, and no fixed five-panel shell. The
    fairness and honesty elements — labels, settings echo, limitation note, error
    text with status — are kept (`UI-UX Brief` §16.1).
24. **One extra Python dependency.** The UI needs `streamlit>=1.40` in the same
    venv. There is no Node, no build step and no separate server process.

## Measured limits (22 October 2026)

`scripts/measure_limits.py`, `timbre-v3.0` / `Lakshmi` / `en-IN` / `1.0`:

1. **~800 characters** costs 4.4–4.8 MB of WAV and 4.4–6.9 s. A comparison pair
   is therefore about **9.4 MB and 10–14 s** — worth knowing before recording a
   60-second demo on a slow connection.
2. **Longer scripts do not scale predictably.** 1,897 characters took 11.0 s and
   11.2 MB; exactly 2,000 characters took 9.2 s and 12.0 MB — the shorter request
   was the slower one. Time carries roughly ±20% run-to-run noise, so only the
   size is predictable: about **6 KB of WAV per character**. Do not extrapolate a
   per-character latency; the honest range is 4.4–11.0 s over 787–2,000 characters.
3. **2,000 characters is the verified maximum the app sends, and it succeeds**
   (2,000 → HTTP 200 in 9.2 s). The upstream ceiling lies somewhere between 2,000
   and 2,100; 2,100 is rejected in 133 ms with a generic 502 ("Timbre is
   temporarily unavailable") — a fast, permanent failure wearing the costume of a
   retryable one. The local block turns that into a truthful message. The
   2,001–2,099 band is untested and unreachable through the app.
4. **A 2,000-character comparison pair** is about **24 MB and 18 s**. Nothing
   stops a user doing it; the 800-character warning is the signal that the demo
   has just become expensive.
5. These are 5 + 3 + 1 samples, not population percentiles. The "p95" in NFR-01 is
   the slowest of five, so it is a lower bound on the real p95. The 2,000 result
   also proves that *that* text works — not that every possible 2,000-character
   string does.

## Scope

Not in this release: speech-model training or tuning, voice cloning, accounts,
roles, sharing, hosted storage, cloud deployment, CI/CD, other languages, or any
paid third-party service.

## Credit safety

`scripts/poc_matrix.py`, `scripts/try_respelling.py` and
`scripts/measure_limits.py` refuse to make a paid call until a human types
`spend`; a non-interactive run cancels with no call made. The repository rules
for AI assistants are in `AGENTS.md`. This is a guard against accident, not a
security boundary: a person can still type `spend`, and `--confirm-spend` exists
for deliberate scripted runs.
