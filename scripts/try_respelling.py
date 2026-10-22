"""Milestone 3 retry - user-authored respellings.

Gate B round 1 failed for a reason that has since been identified: the
respellings were written by the builder, not by the person who wants the
pronunciation. Round 2 (the mechanism check) proved the substitution works -
7 of 8 adjusted files pronounced the word exactly as the respelling spelled it,
1 partly, 0 failures.

The remaining question is therefore the product's real question: when the
user authors the respelling themselves, does the result land closer to what
they intended? This script drives that loop.

It holds model, voice, language and speed constant for every pair, applies
the substitution with the backend's real rule engine, and caches by text so a
term is never paid for twice - the original of a sentence is synthesised once
and reused across every respelling attempt for that term.

Usage (from the project root):
    .venv/Scripts/python.exe scripts/try_respelling.py terms
    .venv/Scripts/python.exe scripts/try_respelling.py original
    .venv/Scripts/python.exe scripts/try_respelling.py adjusted --all
    .venv/Scripts/python.exe scripts/try_respelling.py adjusted --respelling "Timbre=Tim-ber"
    .venv/Scripts/python.exe scripts/try_respelling.py interactive
    .venv/Scripts/python.exe scripts/try_respelling.py sheet
    .venv/Scripts/python.exe scripts/try_respelling.py verdict --verdict "Zentara=closer|note"
    .venv/Scripts/python.exe scripts/try_respelling.py --dry-run

Exit codes:
    0  everything requested was generated
    1  one or more generations failed
    2  GNANI_API_KEY is missing (and --dry-run was not used)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
AUDIO_DIR = PROJECT_ROOT / "data" / "audio"
TRY_DIR = AUDIO_DIR / "try"
RESULTS_JSON = PROJECT_ROOT / "data" / "try_results.json"
POC_RESULTS_JSON = PROJECT_ROOT / "data" / "poc_results.json"
SHEET_HTML = TRY_DIR / "listen.html"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import load_settings  # noqa: E402
from app.core.audio_cache import AudioCache  # noqa: E402
from app.core.gnani_tts import DEFAULT_AUDIO_CONFIG, TimbreClient  # noqa: E402
from app.core.pronunciation_rules import Rule, apply_rules  # noqa: E402
from app.errors import AppError, ConfigurationError  # noqa: E402

# Held constant for every pair. Changing any of these invalidates the
# comparison, exactly as in the first POC run.
SETTINGS: dict[str, Any] = {
    "model": "timbre-v3.0",
    "voice": "Lakshmi",
    "language": "en-IN",
    "speed": 1.0,
}

# Candidate terms for the retry. Two of the round-1 terms are deliberately
# dropped: Nuvora and Aniruddh were already pronounced correctly by this
# voice, so a rule for them proves nothing. Every term here is a suggestion -
# the respelling is the user's to write, and `suggested` is only the value
# the script offers as a starting point.
TERMS: list[dict[str, str]] = [
    {
        "category": "Invented brand",
        "term": "Zentara",
        "sentence": "We shipped Zentara to every customer on the same day.",
        "suggested": "Zen Taara",
    },
    {
        "category": "Product name",
        "term": "Timbre",
        "sentence": "Timbre speaks Indian languages clearly and naturally.",
        "suggested": "Tim-ber",
    },
    {
        "category": "Product name",
        "term": "Gnani",
        "sentence": "Gnani builds speech systems for the Indian market.",
        "suggested": "Gyaa-nee",
    },
    {
        "category": "Indian personal name",
        "term": "Shreyas",
        "sentence": "Shreyas joined the platform team last month.",
        "suggested": "Shrey-as",
    },
    {
        "category": "Indian personal name",
        "term": "Iyer",
        "sentence": "Iyer led the design review for the new console.",
        "suggested": "I-yer",
    },
    {
        "category": "Place name",
        "term": "Coimbatore",
        "sentence": "The Coimbatore campus opens next quarter.",
        "suggested": "Koyamba-tore",
    },
    {
        "category": "Acronym read as a word",
        "term": "SEBI",
        "sentence": "SEBI published the circular on Friday evening.",
        "suggested": "Say-bee",
    },
    {
        "category": "Technical term",
        "term": "Kubernetes",
        "sentence": "The cluster runs on Kubernetes with autoscaling enabled.",
        "suggested": "Koo-ber-NET-eez",
    },
]

VERDICTS = ("closer", "no change", "worse", "damaged")


def confirm_credit_spend(estimate: int, *, detail: str = "") -> None:
    """Stop before the first paid call unless a human types the word.

    An agent, a heredoc or a pipe cannot answer this: `input()` raises EOFError
    and the run aborts with no call made. `--confirm-spend` is the deliberate,
    visible opt-in for a scripted run, and AGENTS.md forbids using it without
    the user's explicit approval in the current conversation.
    """
    if estimate <= 0:
        print("Nothing to generate: every file this run needs is already cached. "
              "No credits will be spent.")
        return

    print(f"This run can make up to {estimate} paid Timbre call(s).")
    if detail:
        print(detail)
    print("Nothing has been sent yet. No credits have been spent.")
    try:
        answer = input('Type "spend" to continue, or press Enter to cancel: ')
    except EOFError:
        answer = ""
    if answer.strip().lower() != "spend":
        raise SystemExit("Cancelled before any API call. No credits were spent.")


def _original_is_cached(
    manifest: dict[str, Any], settings: dict[str, Any], item: dict[str, str]
) -> bool:
    original = manifest["terms"].get(item["term"], {}).get("original", {})
    destination = (
        TRY_DIR / f"{term_index(item['term']):02d}_{slug(item['term'])}_original.wav"
    )
    return (
        original.get("key") == cache_key_for(item["sentence"], settings)
        and destination.is_file()
    )


def estimate_calls(
    manifest: dict[str, Any],
    settings: dict[str, Any],
    action: str,
    respellings: list[tuple[str, str]],
    use_all: bool,
    only: str | None,
) -> tuple[int, str]:
    """Upper bound on paid calls, so the guard can state the cost honestly."""
    possible = []

    if action == "adjusted":
        possible = [(item["term"], item["suggested"]) for item in TERMS] if use_all else respellings
        if only:
            possible = [pair for pair in possible if pair[0] == only]

    scoped = {term for term, _ in possible} if action == "adjusted" else None
    missing_originals = sum(
        1
        for item in TERMS
        if (scoped is None or item["term"] in scoped)
        and not _original_is_cached(manifest, settings, item)
    )

    if action == "original":
        return missing_originals, f"{missing_originals} original(s) are not cached yet."

    if action == "adjusted":
        pairs = possible
        new_attempts = 0
        for term, respelling in pairs:
            item = next((candidate for candidate in TERMS if candidate["term"] == term), None)
            if item is None:
                continue
            transformed = transform(item["sentence"], term, respelling)
            key = cache_key_for(transformed, settings)
            destination = TRY_DIR / (
                f"{term_index(term):02d}_{slug(term)}_{slug(respelling)}_adjusted.wav"
            )
            previous = next(
                (
                    attempt
                    for attempt in manifest["terms"].get(term, {}).get("attempts", [])
                    if attempt.get("respelling") == respelling
                ),
                {},
            )
            if not (previous.get("key") == key and destination.is_file()):
                new_attempts += 1
        return (
            missing_originals + new_attempts,
            f"{missing_originals} original(s) and {new_attempts} respelling(s) "
            "are not cached yet.",
        )

    if action == "interactive":
        pending = sum(
            1
            for item in TERMS
            if manifest["terms"].get(item["term"], {}).get("verdict") not in VERDICTS
        )
        return (
            missing_originals + pending,
            f"{missing_originals} original(s) are not cached; {pending} term(s) "
            "still need a verdict and may each get one new respelling.",
        )

    return 0, ""


def slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")


def load_manifest() -> dict[str, Any]:
    if not RESULTS_JSON.is_file():
        return {"terms": {}, "settings": dict(SETTINGS)}
    try:
        payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    except ValueError:
        return {"terms": {}, "settings": dict(SETTINGS)}
    payload.setdefault("terms", {})
    return payload


def save_manifest(manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def build_client() -> TimbreClient:
    try:
        app_settings = load_settings()
    except ConfigurationError as exc:
        raise SystemExit(f"{exc}\nAdd the key to backend/.env, or use --dry-run.") from exc
    return TimbreClient(
        api_key=app_settings.api_key,
        base_url=app_settings.base_url,
        timeout_seconds=app_settings.timeout_seconds,
    )


def cache_key_for(text: str, settings: dict[str, Any]) -> str:
    return AudioCache.key(
        text=text,
        model=settings["model"],
        voice=settings["voice"],
        language=settings["language"],
        speed=settings["speed"],
        audio_config=DEFAULT_AUDIO_CONFIG,
    )


def transform(sentence: str, term: str, respelling: str) -> str:
    result = apply_rules(sentence, [Rule(source=term, replacement=respelling)])
    return result.transformed_text


def synthesise(
    client: TimbreClient, text: str, settings: dict[str, Any]
) -> tuple[int, bytes, int, str]:
    """Return (status, audio, elapsed_ms, error_message)."""
    try:
        outcome = client.synthesize(
            text=text,
            model=settings["model"],
            voice=settings["voice"],
            language=settings["language"],
            speed=settings["speed"],
            audio_config=DEFAULT_AUDIO_CONFIG,
        )
    except AppError as exc:
        return 0, b"", 0, f"{exc.error_type}: {exc.message}"
    return outcome.status, outcome.audio, outcome.elapsed_ms, ""


def cached_or_new(
    client: TimbreClient,
    *,
    text: str,
    settings: dict[str, Any],
    destination: Path,
    cache_key: str,
    bucket: dict[str, Any],
) -> dict[str, Any]:
    """Synthesise once per (text, settings) and reuse the file after that."""
    if bucket.get("key") == cache_key and destination.is_file():
        bucket["reused"] = True
        return bucket

    status, audio, elapsed_ms, error = synthesise(client, text, settings)
    if not audio:
        bucket.update({"key": cache_key, "status": status, "error": error})
        bucket.pop("file", None)
        return bucket

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(audio)
    bucket.update(
        {
            "key": cache_key,
            "file": destination.relative_to(AUDIO_DIR).as_posix(),
            "status": status,
            "bytes": len(audio),
            "elapsed_ms": elapsed_ms,
            "error": "",
        }
    )
    bucket.pop("reused", None)
    return bucket


def term_entry(manifest: dict[str, Any], term: str) -> dict[str, Any]:
    return manifest["terms"].setdefault(
        term,
        {
            "term": term,
            "category": "",
            "sentence": "",
            "suggested": "",
            "original": {},
            "attempts": [],
            "verdict": "pending",
            "notes": "",
        },
    )


def seed_terms(manifest: dict[str, Any]) -> None:
    for item in TERMS:
        entry = term_entry(manifest, item["term"])
        entry["category"] = item["category"]
        entry["sentence"] = item["sentence"]
        entry["suggested"] = item["suggested"]


def term_index(term: str) -> int:
    for index, item in enumerate(TERMS, start=1):
        if item["term"] == term:
            return index
    return 0


def seed_from_poc(manifest: dict[str, Any], settings: dict[str, Any]) -> int:
    """Reuse round-1 originals whose sentence and settings are unchanged.

    Four of the eight retry sentences are byte-identical to round-1
    sentences, generated with the same model, voice, language and speed. The
    audio is the same, so it is copied over instead of being paid for again.
    """
    if not POC_RESULTS_JSON.is_file():
        return 0
    try:
        payload = json.loads(POC_RESULTS_JSON.read_text(encoding="utf-8"))
    except ValueError:
        return 0
    if payload.get("settings") != settings:
        return 0

    by_sentence = {
        record["sentence"]: record
        for record in payload.get("terms", [])
        if record.get("sentence") and record.get("original_file")
    }

    reused = 0
    for item in TERMS:
        record = by_sentence.get(item["sentence"])
        if record is None:
            continue
        source = AUDIO_DIR / record["original_file"]
        if not source.is_file():
            continue
        entry = term_entry(manifest, item["term"])
        destination = (
            TRY_DIR / f"{term_index(item['term']):02d}_{slug(item['term'])}_original.wav"
        )
        if (
            entry["original"].get("key") == cache_key_for(item["sentence"], settings)
            and destination.is_file()
        ):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        entry["original"] = {
            "key": cache_key_for(item["sentence"], settings),
            "file": destination.relative_to(AUDIO_DIR).as_posix(),
            "status": 200,
            "bytes": destination.stat().st_size,
            "elapsed_ms": None,
            "error": "",
            "reused_from": record["original_file"],
        }
        reused += 1
    return reused


def ensure_original(
    manifest: dict[str, Any],
    client: TimbreClient | None,
    settings: dict[str, Any],
    item: dict[str, str],
) -> dict[str, Any]:
    entry = term_entry(manifest, item["term"])
    key = cache_key_for(item["sentence"], settings)
    destination = TRY_DIR / f"{term_index(item['term']):02d}_{slug(item['term'])}_original.wav"
    if client is None:
        entry["original"].update(
            {
                "key": key,
                "file": destination.relative_to(AUDIO_DIR).as_posix(),
                "status": None,
                "dry_run": True,
            }
        )
        return entry["original"]
    return cached_or_new(
        client,
        text=item["sentence"],
        settings=settings,
        destination=destination,
        cache_key=key,
        bucket=entry["original"],
    )


def add_attempt(
    manifest: dict[str, Any],
    client: TimbreClient | None,
    settings: dict[str, Any],
    item: dict[str, str],
    respelling: str,
) -> dict[str, Any]:
    entry = term_entry(manifest, item["term"])
    transformed = transform(item["sentence"], item["term"], respelling)
    key = cache_key_for(transformed, settings)
    # One file per respelling, so a second attempt for the same term never
    # overwrites the first.
    destination = TRY_DIR / (
        f"{term_index(item['term']):02d}_{slug(item['term'])}"
        f"_{slug(respelling)}_adjusted.wav"
    )

    attempt: dict[str, Any] = {
        "respelling": respelling,
        "transformed_text": transformed,
        "verdict": "pending",
        "notes": "",
    }
    # Carry the previous attempt's cache key so a respelling that was already
    # generated is reused instead of paid for twice.
    previous = next(
        (a for a in entry["attempts"] if a["respelling"] == respelling), None
    )
    if previous is not None:
        # Carry the whole cache record so a re-run reuses the existing file
        # instead of paying for it again, and a recorded verdict survives.
        for field in ("key", "file", "status", "bytes", "elapsed_ms", "error"):
            if field in previous:
                attempt[field] = previous[field]
        attempt["verdict"] = previous.get("verdict", "pending")
        attempt["notes"] = previous.get("notes", "")
    if client is None:
        attempt.update(
            {
                "key": key,
                "file": destination.relative_to(AUDIO_DIR).as_posix(),
                "status": None,
                "dry_run": True,
            }
        )
    else:
        cached_or_new(
            client,
            text=transformed,
            settings=settings,
            destination=destination,
            cache_key=key,
            bucket=attempt,
        )

    entry["attempts"] = [
        a for a in entry["attempts"] if a["respelling"] != respelling
    ]
    entry["attempts"].append(attempt)
    return attempt


def cmd_terms(manifest: dict[str, Any]) -> int:
    print("Terms for the retry. The respelling is yours to write.\n")
    for index, item in enumerate(TERMS, start=1):
        print(f"{index}. {item['term']}  ({item['category']})")
        print(f"   sentence:   {item['sentence']}")
        print(f"   suggestion: {item['suggested']}")
    print(
        "\nTerms dropped from round 1: Nuvora and Aniruddh - this voice already "
        "pronounced both correctly, so a rule for them proves nothing."
    )
    return 0


def cmd_original(
    manifest: dict[str, Any], client: TimbreClient | None, settings: dict[str, Any]
) -> int:
    seed_terms(manifest)
    failures = 0
    reused = seed_from_poc(manifest, settings)
    if reused:
        print(f"Reused {reused} original(s) from the round-1 run - no credits spent.\n")
    print(
        "Originals. Each sentence is paid for once and reused for every "
        "respelling attempt.\n"
    )
    for index, item in enumerate(TERMS, start=1):
        bucket = ensure_original(manifest, client, settings, item)
        if client is None:
            print(f"[{index}/{len(TERMS)}] {item['term']}: dry run, no call made")
            continue
        if bucket.get("error") or not bucket.get("file"):
            failures += 1
            print(f"[{index}/{len(TERMS)}] {item['term']}: FAILED {bucket}")
            continue
        print(
            f"[{index}/{len(TERMS)}] {item['term']}: {bucket['file']} "
            f"({bucket.get('bytes', 0):,} bytes, {bucket.get('elapsed_ms', 0)} ms)"
            + ("  [reused]" if bucket.get("reused") else "")
        )
    if client is not None:
        save_manifest(manifest)
    return 1 if failures else 0


def parse_respellings(values: list[str]) -> list[tuple[str, str]]:
    """Return (term, respelling) pairs. A term may appear more than once."""
    pairs: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise SystemExit(f'--respelling must be "Term=Respelling", got: {value}')
        term, respelling = value.split("=", 1)
        pairs.append((term.strip(), respelling.strip()))
    return pairs


def cmd_adjusted(
    manifest: dict[str, Any],
    client: TimbreClient | None,
    settings: dict[str, Any],
    respellings: list[tuple[str, str]],
    use_all: bool,
    only: str | None,
) -> int:
    seed_terms(manifest)
    if use_all:
        respellings = [(item["term"], item["suggested"]) for item in TERMS]
    if not respellings:
        raise SystemExit(
            'Nothing to do. Pass --respelling "Term=Respelling" or --all.'
        )

    known = {item["term"] for item in TERMS}
    unknown = sorted({term for term, _ in respellings} - known)
    if unknown:
        raise SystemExit(
            "Unknown term(s): "
            + ", ".join(unknown)
            + ". Run `try_respelling.py terms` for the list."
        )
    if only:
        respellings = [pair for pair in respellings if pair[0] == only]
        if not respellings:
            raise SystemExit(f"No respelling given for {only}.")

    failures = 0
    print("Adjusted files. One call per distinct respelling.\n")
    for term, respelling in respellings:
        item = next(i for i in TERMS if i["term"] == term)
        ensure_original(manifest, client, settings, item)
        attempt = add_attempt(manifest, client, settings, item, respelling)
        if client is None:
            print(f"{term} -> {respelling}  (dry run, no call made)")
            continue
        if attempt.get("error") or not attempt.get("file"):
            failures += 1
            print(f"{term} -> {respelling}: FAILED {attempt}")
            continue
        print(
            f"{term} -> {respelling}: {attempt['file']} "
            f"({attempt.get('bytes', 0):,} bytes, {attempt.get('elapsed_ms', 0)} ms)"
            + ("  [reused]" if attempt.get("reused") else "")
        )
    if client is not None:
        save_manifest(manifest)
    return 1 if failures else 0


def cmd_interactive(
    manifest: dict[str, Any],
    client: TimbreClient | None,
    settings: dict[str, Any],
    redo: bool = False,
) -> int:
    """The product loop, in a terminal: type a respelling, then judge it in a browser.

    No audio is ever handed to an external player. The listening sheet is
    rebuilt after every term, so the whole comparison - original against
    adjusted - is judged on one page, in the browser, at the listener's pace.
    """
    seed_terms(manifest)
    reused = seed_from_poc(manifest, settings)
    if reused:
        print(f"Reused {reused} original(s) from the round-1 run - no credits spent.")
    print("Interactive respelling loop.")
    print("Type the respelling you want for each term.")
    print("Nothing is played here - the listening sheet is rebuilt after each term.")
    print("Type 'q' at any respelling prompt to stop; progress is saved.")
    print("Each new respelling costs one Timbre call; audio already generated "
          "is reused.\n")

    failures = 0
    for index, item in enumerate(TERMS, start=1):
        entry = term_entry(manifest, item["term"])
        if not redo and entry.get("verdict") in VERDICTS:
            print(
                f"--- [{index}/{len(TERMS)}] {item['term']}  "
                f"already recorded: {entry['verdict']} - skipped"
            )
            continue

        print(f"--- [{index}/{len(TERMS)}] {item['term']}  ({item['category']})")
        print(f"    sentence: {item['sentence']}")
        already = entry.get("attempts", [])
        if already:
            tried = ", ".join(str(attempt.get("respelling", "")) for attempt in already)
            print(f"    already tried: {tried}")

        original = ensure_original(manifest, client, settings, item)
        if original.get("error"):
            failures += 1
            print(f"    original FAILED: {original.get('error')}")
            continue

        try:
            answer = input(f"    respelling [{item['suggested']}]: ").strip()
        except EOFError:
            answer = ""
        respelling = answer or item["suggested"]
        if respelling.lower() in {"q", "quit", "exit"}:
            print("  stopped early.")
            break

        attempt = add_attempt(manifest, client, settings, item, respelling)
        if attempt.get("error") or not attempt.get("file"):
            failures += 1
            print(f"    adjusted FAILED: {attempt.get('error')}")
            continue

        print(f"    said as: {respelling}")
        if client is not None:
            save_manifest(manifest)
        write_sheet(manifest)
        print()

    if client is not None:
        save_manifest(manifest)
    _print_progress(manifest)
    write_sheet(manifest)
    print(f"\nListening sheet: {SHEET_HTML}")
    print("Open it in a browser: play the original, then the adjusted clip.")
    print("Then record each verdict with:")
    print(
        '  .venv/Scripts/python.exe scripts/try_respelling.py verdict '
        '--verdict "Zentara=closer|note"'
    )
    return 1 if failures else 0


def _print_progress(manifest: dict[str, Any]) -> None:
    recorded = [
        item
        for item in TERMS
        if manifest["terms"].get(item["term"], {}).get("verdict") in VERDICTS
    ]
    pending = [item["term"] for item in TERMS if item not in recorded]
    print(f"\nRecorded {len(recorded)} of {len(TERMS)}.")
    if pending:
        print("Still open: " + ", ".join(pending))
    else:
        print("All eight terms have a verdict.")


def cmd_verdict(manifest: dict[str, Any], values: list[str]) -> int:
    """Record verdicts after listening, then refresh the sheet that shows them."""
    if not values:
        raise SystemExit('Pass --verdict "Term=closer|note".')
    for value in values:
        if "=" not in value:
            raise SystemExit(f'--verdict must be "Term=verdict|note", got: {value}')
        term, payload = value.split("=", 1)
        term = term.strip()
        verdict, _, notes = payload.partition("|")
        verdict = verdict.strip().lower()
        if verdict not in VERDICTS:
            raise SystemExit(
                f'Verdict for {term} must be one of {", ".join(sorted(VERDICTS))}, '
                f"got: {verdict}"
            )
        entry = term_entry(manifest, term)
        entry["verdict"] = verdict
        entry["notes"] = notes.strip()
        marked = ""
        if entry["attempts"]:
            entry["attempts"][-1]["verdict"] = entry["verdict"]
            entry["attempts"][-1]["notes"] = entry["notes"]
            marked = f" (marked attempt: {entry['attempts'][-1].get('respelling', '')})"
        print(
            f"{term}: {entry['verdict']}{marked}"
            + (f" - {entry['notes']}" if entry["notes"] else "")
        )
    save_manifest(manifest)
    write_sheet(manifest)
    return 0


def write_sheet(manifest: dict[str, Any]) -> Path:
    """Rebuild the listening sheet and return the path written."""
    def player(file: str | None) -> str:
        """Audio tag with a path relative to the sheet's own folder."""
        if not file:
            return "<em>not generated</em>"
        path = AUDIO_DIR / file
        if not path.is_file():
            return "<em>not generated</em>"
        relative = path.relative_to(SHEET_HTML.parent).as_posix()
        return f'<audio controls preload="none" src="{relative}"></audio>'

    rows: list[str] = []
    for item in TERMS:
        entry = manifest["terms"].get(item["term"], {})
        original_cell = player(entry.get("original", {}).get("file"))

        attempts = entry.get("attempts", [])
        if attempts:
            attempt_cells = []
            for attempt in attempts:
                attempt_cells.append(
                    f'<div class="attempt">{player(attempt.get("file"))}'
                    f'<span class="repl">{attempt.get("respelling", "")}</span>'
                    f'<span class="verdict">{attempt.get("verdict", "pending")}</span></div>'
                )
            adjusted_cell = "".join(attempt_cells)
        else:
            adjusted_cell = "<em>no respelling yet</em>"

        verdict_badge = ""
        if entry.get("verdict") in VERDICTS:
            verdict_badge = f'<br><span class="verdict">{entry["verdict"]}</span>'

        rows.append(
            f'  <tr><td class="num">{len(rows) + 1}</td>'
            f'<td><strong>{item["term"]}</strong><br><span class="cat">{item["category"]}</span>{verdict_badge}</td>'
            f"<td>{original_cell}</td><td>{adjusted_cell}</td>"
            f'<td class="int">{item["sentence"]}</td></tr>'
        )

    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Gate B retry - listening sheet</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1200px; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; margin-bottom: .25rem; }}
  p.lead {{ color: #444; max-width: 80ch; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1.5rem; }}
  th, td {{ border-bottom: 1px solid #ddd; padding: .6rem .5rem; text-align: left; vertical-align: top; }}
  th {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #555; }}
  td.num {{ font-weight: 700; width: 2rem; }}
  span.cat {{ font-size: .78rem; color: #666; }}
  td.int {{ color: #333; font-size: .9rem; }}
  audio {{ width: 200px; display: block; margin-bottom: .3rem; }}
  .attempt {{ margin-bottom: .8rem; }}
  .repl {{ font-weight: 700; margin-right: .6rem; }}
  .verdict {{ font-size: .8rem; color: #666; }}
  .note {{ background: #f6f6f6; padding: .8rem 1rem; border-left: 4px solid #888; margin: 1.2rem 0; }}
</style>
<h1>Gate B retry - user-authored respellings</h1>
<p class="lead">
  Play the <strong>original</strong>, then each <strong>adjusted</strong> attempt.
  Question: is the adjusted pronunciation closer to what you want than the original?
</p>
<div class="note">
  Settings identical for every pair: {SETTINGS['model']}, {SETTINGS['voice']},
  {SETTINGS['language']}, speed {SETTINGS['speed']}.
  The original of each sentence was synthesised once and reused for every attempt.
  <br><br>
  These WAVs come from the upstream service with a placeholder size in the RIFF
  header. If a clip will not seek, that is the known placeholder-header quirk,
  not a broken file - it plays to the end.
  <br><br>
  Record each verdict with:
  <code>try_respelling.py verdict --verdict "Zentara=closer|note"</code>
</div>
<table>
  <tr><th>#</th><th>Term</th><th>Original</th><th>Adjusted attempts</th><th>Sentence</th></tr>
{chr(10).join(rows)}
</table>
</html>
"""
    SHEET_HTML.parent.mkdir(parents=True, exist_ok=True)
    SHEET_HTML.write_text(html, encoding="utf-8")
    return SHEET_HTML


def cmd_sheet(manifest: dict[str, Any]) -> int:
    write_sheet(manifest)
    print(f"Wrote {SHEET_HTML}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate B retry with user respellings")
    parser.add_argument("--dry-run", action="store_true", help="no API calls")
    parser.add_argument(
        "--confirm-spend",
        action="store_true",
        help="skip the typed credit confirmation (only with the user's explicit go-ahead)",
    )
    parser.add_argument("--model", default=SETTINGS["model"])
    parser.add_argument("--voice", default=SETTINGS["voice"])
    parser.add_argument("--speed", type=float, default=SETTINGS["speed"])
    parser.add_argument(
        "--respelling", action="append", default=[], metavar="TERM=RESPELLING"
    )
    parser.add_argument(
        "--verdict", action="append", default=[], metavar="TERM=VERDICT|NOTE"
    )
    parser.add_argument("--term", default=None, help="restrict to one term")
    parser.add_argument(
        "--all", action="store_true", help="use the suggested respelling for every term"
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="in interactive mode, redo terms that already have a verdict",
    )
    parser.add_argument(
        "action",
        choices=["terms", "original", "adjusted", "interactive", "sheet", "verdict"],
        help="what to do",
    )
    args = parser.parse_args()

    settings = dict(SETTINGS)
    settings.update(model=args.model, voice=args.voice, speed=args.speed)
    manifest = load_manifest()
    manifest["settings"] = settings

    if args.action == "terms":
        return cmd_terms(manifest)

    if args.action == "sheet":
        return cmd_sheet(manifest)

    if args.action == "adjusted" and args.verdict:
        return cmd_verdict(manifest, args.verdict)

    if args.action == "verdict":
        return cmd_verdict(manifest, args.verdict)

    respellings = parse_respellings(args.respelling)

    client: TimbreClient | None = None
    if not args.dry_run:
        client = build_client()
        estimate, detail = estimate_calls(
            manifest, settings, args.action, respellings, args.all, args.term
        )
        if args.confirm_spend:
            print(f"Confirmed in advance: up to {estimate} paid call(s). {detail}")
        else:
            confirm_credit_spend(estimate, detail=detail)

    if args.action == "original":
        return cmd_original(manifest, client, settings)

    if args.action == "interactive":
        return cmd_interactive(manifest, client, settings, redo=args.redo)

    return cmd_adjusted(manifest, client, settings, respellings, args.all, args.term)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AppError as exc:  # pragma: no cover - developer script
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
