"""Milestone 10 - measure the limits the docs had only guessed at.

Answers three questions from `TRD` section 20 / `Backend Schema` section 17:

  TQ4  Is synthesis of an 800-character script inside the 10 s p95 target
       (NFR-01)? Before the first run the only timings on record were a short
       sentence at 875 ms and 1,330 characters at 7,153 ms - one sample each.
  TQ5  Does the API accept scripts above the app's 2,000-character block, or
       does it reject them? The app blocks above 2,000 on the assumption that
       the API would refuse, and that assumption is user-facing.
  TQ5b Exactly 2,000 characters - the largest script the app will ever send.
       If that fails upstream, the block is too permissive: the user would
       reach an opaque error with a script the app itself allowed.

Runs, 22 October 2026 (timbre-v3.0 / Lakshmi / en-IN / 1.0):
  TQ4  median 6,157 ms, slowest of five 6,905 ms -> inside the 10 s target
  TQ5  1,897 characters: 200 in 10,970 ms, 11.2 MB
       2,100 characters: 502 in 133 ms - a fast rejection, not a timeout
  TQ5b 2,000 characters: 200 in 9,197 ms, 12.0 MB - so the app's block is a
       verified ceiling, and the upstream threshold lies in (2,000, 2,100].
       Note that 2,000 came back 1.8 s FASTER than 1,897: latency is noisy and
       not monotonic in length, so this script reports samples, not a slope.

B4 (does `speed` outside 0.85-1.15 clamp or 400?) is deliberately NOT probed.
Speed is fixed at 1.0 and range-validated before any call in this release, so
the answer changes no shipped behaviour and is not worth a credit.

How it measures
    TQ4  Five DISTINCT scripts of 780-800 characters. Distinct matters: an
         identical script hits the audio cache and measures the cache instead
         of the network. With five samples, nearest-rank p95 is simply the
         slowest sample, so the script reports every timing plus the median.
    TQ5  One script at ~1,900 characters, one at exactly 2,000 (the app's own
         maximum), and one at ~2,100. 2,100 is above the app's block limit on
         purpose - the block is enforced by the API layer, not by the client,
         so the client can ask the upstream question directly.

Every response is written to the normal audio cache, so a repeat run only pays
for scripts it has not generated before. For scripts it does have, the timing a
previous run recorded is kept rather than overwritten with an empty one - a free
rehearsal must not erase the numbers the docs cite.

Usage (from the project root):
    .venv/Scripts/python.exe scripts/measure_limits.py --dry-run
    .venv/Scripts/python.exe scripts/measure_limits.py

Exit codes:
    0  every probe ran (and the timings were recorded)
    1  one or more probes failed upstream
    2  GNANI_API_KEY is missing
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
RESULTS_JSON = PROJECT_ROOT / "data" / "limits_results.json"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Loaded by path in the tests, where the script's own folder is not on sys.path.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _guard import confirm_credit_spend  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.core.audio_cache import AudioCache  # noqa: E402
from app.core.gnani_tts import DEFAULT_AUDIO_CONFIG, TimbreClient  # noqa: E402
from app.errors import AppError, ConfigurationError  # noqa: E402

# Held constant, as in every other comparison in this project.
SETTINGS: dict[str, Any] = {
    "model": "timbre-v3.0",
    "voice": "Lakshmi",
    "language": "en-IN",
    "speed": 1.0,
}

NFR_01_TARGET_MS = 10_000
P95_TARGET_CHARS = 800
P95_SAMPLES = 5

# Synthetic, neutral, Indian-English filler. No personal data (PRD section 12.3).
POOL: tuple[str, ...] = (
    "The studio keeps the original script untouched while sending the transformed script to the engine. ",
    "A saved dictionary applies the same pronunciation rules to every later script without re-entry. ",
    "Each comparison pair is generated with one model, one voice, one language and one speed setting. ",
    "Replacements are inserted exactly as the author wrote them, including their capitalisation. ",
    "Matches are reported per rule so a term that never appears in the script is visible immediately. ",
    "Audio is cached by text and settings, so replaying a clip never spends a second credit. ",
    "The limitation note stays on screen because the product rewrites text rather than phonemes. ",
    "Errors are shown with the HTTP status and a plain-language cause instead of a stack trace. ",
)


def build_text(target: int, rotation: int) -> str:
    """Join pool sentences in a rotated order, then trim to at most `target`.

    Rotation makes each sample a different string, so the cache cannot answer
    for it. Trimming happens on a word boundary so the script never ends
    mid-word, and the result is always <= target - which is what NFR-01
    actually specifies.
    """
    ordered = POOL[rotation:] + POOL[:rotation]
    parts: list[str] = []
    length = 0
    index = 0
    while length < target:
        sentence = ordered[index % len(ordered)]
        parts.append(sentence)
        length += len(sentence)
        index += 1

    text = "".join(parts)
    if len(text) > target:
        cut = text.rfind(" ", 0, target + 1)
        text = text[:cut] if cut > 0 else text[:target]
    return text.strip()


def planned_probes() -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for sample in range(P95_SAMPLES):
        probes.append(
            {
                "question": "TQ4",
                "label": f"p95-{sample + 1}",
                "text": build_text(P95_TARGET_CHARS, sample),
            }
        )
    probes.append(
        {"question": "TQ5", "label": "ceiling-1900", "text": build_text(1900, 2)}
    )
    # Exactly the largest script the app will ever send (SCRIPT_BLOCK_CHARS).
    # If this fails, the app's own block is too permissive and a user can reach
    # the upstream's opaque failure by typing fewer characters than it allows.
    probes.append(
        {"question": "TQ5", "label": "ceiling-2000", "text": build_text(2000, 3)}
    )
    probes.append(
        {"question": "TQ5", "label": "ceiling-2100", "text": build_text(2100, 5)}
    )
    return probes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure the NFR-01 latency and the real length ceiling"
    )
    parser.add_argument("--dry-run", action="store_true", help="no API calls")
    parser.add_argument(
        "--confirm-spend",
        action="store_true",
        help="skip the typed credit confirmation (only with the owner's explicit go-ahead)",
    )
    parser.add_argument("--model", default=SETTINGS["model"])
    parser.add_argument("--voice", default=SETTINGS["voice"])
    parser.add_argument("--speed", type=float, default=SETTINGS["speed"])
    parser.add_argument(
        "--probe",
        action="append",
        default=[],
        metavar="LABEL",
        help="run only these probes (labels from the plan, e.g. ceiling-2000)",
    )
    args = parser.parse_args()

    settings = dict(SETTINGS)
    settings.update(model=args.model, voice=args.voice, speed=args.speed)

    try:
        app_settings = load_settings()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    cache = AudioCache(app_settings.data_dir / "audio")
    probes = planned_probes()

    if args.probe:
        wanted = {label.strip() for label in args.probe}
        unknown = wanted - {probe["label"] for probe in probes}
        if unknown:
            print(
                "Unknown probe label(s): " + ", ".join(sorted(unknown)),
                file=sys.stderr,
            )
            return 2
        probes = [probe for probe in probes if probe["label"] in wanted]

    for probe in probes:
        probe["char_count"] = len(probe["text"])
        probe["cache_key"] = AudioCache.key(
            text=probe["text"],
            model=settings["model"],
            voice=settings["voice"],
            language=settings["language"],
            speed=settings["speed"],
            audio_config=DEFAULT_AUDIO_CONFIG,
        )
        probe["cached"] = cache.get(probe["cache_key"]) is not None

    paid = sum(1 for probe in probes if not probe["cached"])

    print("Plan")
    print(f"  model={settings['model']} voice={settings['voice']} "
          f"language={settings['language']} speed={settings['speed']}")
    for probe in probes:
        state = "cached (free)" if probe["cached"] else "will call (1 credit)"
        print(f"  [{probe['question']}] {probe['label']:<14} "
              f"{probe['char_count']:>5} chars  {state}")
    print(f"  Up to {paid} paid call(s); {len(probes) - paid} already cached.")

    if args.dry_run:
        print("\nDry run: no API call was made and no credits were spent.")
        return 0

    client = TimbreClient(
        app_settings.api_key, app_settings.base_url, app_settings.timeout_seconds
    )
    if args.confirm_spend:
        print(f"Confirmed in advance: up to {paid} paid call(s).")
    else:
        confirm_credit_spend(paid)

    failures = 0
    started_run = time.perf_counter()
    for probe in probes:
        if probe["cached"]:
            probe.update(status="cached", elapsed_ms=None, bytes=None, error="")
            continue

        begin = time.perf_counter()
        try:
            outcome = client.synthesize(
                text=probe["text"], **settings, audio_config=DEFAULT_AUDIO_CONFIG
            )
        except AppError as exc:
            failures += 1
            probe.update(
                status=getattr(exc, "status_code", None),
                elapsed_ms=int((time.perf_counter() - begin) * 1000),
                bytes=None,
                error=str(exc),
            )
            print(f"  {probe['label']}: FAILED - {exc}")
            continue

        try:
            cache.store(
                probe["cache_key"],
                outcome.audio,
                text=probe["text"],
                settings={**settings, **DEFAULT_AUDIO_CONFIG},
                upstream_status=outcome.status,
                elapsed_ms=outcome.elapsed_ms,
            )
        except OSError as exc:
            # The paid call already happened; losing the measurement too would
            # mean paying for it again. Record it and carry on.
            print(f"  {probe['label']}: audio not cached ({exc})", file=sys.stderr)
        probe.update(
            status=outcome.status,
            elapsed_ms=outcome.elapsed_ms,
            bytes=len(outcome.audio),
            error="",
        )
        print(f"  {probe['label']}: {outcome.status} {outcome.elapsed_ms} ms "
              f"{len(outcome.audio)} bytes")

    report = summarise(merge_with_earlier(probes, settings), settings, failures)
    report["total_wall_ms"] = int((time.perf_counter() - started_run) * 1000)

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print()
    print_report(report)
    print(f"\nWrote {RESULTS_JSON}")
    return 1 if failures else 0


def load_earlier_report() -> dict[str, Any]:
    """The previous run's report, or {} when there is none worth trusting."""
    try:
        text = RESULTS_JSON.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        print(
            f"Note: {RESULTS_JSON.name} is not valid JSON; starting a fresh report.",
            file=sys.stderr,
        )
        return {}
    return data if isinstance(data, dict) else {}


def _keep_measurement(
    probe: dict[str, Any], earlier: dict[str, Any] | None
) -> dict[str, Any]:
    """A cached probe has no timing, so keep the earlier measurement.

    Without this a rerun where every script is already cached writes `null`
    over every recorded timing - and the timings are the whole point of the file.
    """
    if probe.get("elapsed_ms") is not None:
        return probe
    if earlier and earlier.get("elapsed_ms") is not None:
        return earlier
    return {**probe, "status": None}


def _outcome_text(probe: dict[str, Any]) -> str:
    if probe.get("error"):
        return probe["error"]
    if probe.get("status") is None:
        return "cached from an earlier run; no timing on file"
    return f"HTTP {probe['status']}"


def merge_with_earlier(
    this_run: list[dict[str, Any]], settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Fill in labels this run did not touch, in the canonical plan order.

    Two rules keep this run from writing a worse report than the one on disk: a
    cached probe keeps its earlier timing, and records made under different
    settings or for a label the plan no longer contains are dropped.
    """
    order = {probe["label"]: index for index, probe in enumerate(planned_probes())}
    earlier = load_earlier_report()
    if earlier and earlier.get("settings") != settings:
        print(
            "Note: settings changed since the last run; earlier probes not merged.",
            file=sys.stderr,
        )
        earlier = {}

    previous = {
        probe["label"]: probe
        for probe in earlier.get("probes", [])
        if isinstance(probe, dict) and probe.get("label") in order
    }
    merged = [_keep_measurement(probe, previous.get(probe["label"])) for probe in this_run]
    touched = {probe["label"] for probe in this_run}
    merged.extend(probe for label, probe in previous.items() if label not in touched)
    return sorted(merged, key=lambda probe: order.get(probe["label"], len(order)))


def summarise(
    probes: list[dict[str, Any]], settings: dict[str, Any], failures: int
) -> dict[str, Any]:
    timed = [
        probe
        for probe in probes
        if probe["question"] == "TQ4" and probe["elapsed_ms"] is not None
    ]
    p95_timings = [probe["elapsed_ms"] for probe in timed]
    ceiling = [
        {
            "label": probe["label"],
            "char_count": probe["char_count"],
            "status": probe["status"],
            "error": probe["error"],
        }
        for probe in probes
        if probe["question"] == "TQ5"
    ]

    slowest = max(p95_timings) if p95_timings else None
    median = int(statistics.median(p95_timings)) if p95_timings else None

    return {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "settings": settings,
        "targets": {
            "nfr_01_ms": NFR_01_TARGET_MS,
            "p95_chars": P95_TARGET_CHARS,
            "samples": P95_SAMPLES,
        },
        "tq4": {
            "char_counts": [probe["char_count"] for probe in timed],
            "elapsed_ms": p95_timings,
            "median_ms": median,
            "p95_ms": slowest,
            "p95_method": (
                f"nearest-rank over {len(p95_timings)} timed sample(s); "
                "below 20 samples the p95 is the slowest sample"
            ),
            "within_target": (
                None if slowest is None else slowest <= NFR_01_TARGET_MS
            ),
        },
        "tq5": {"probes": ceiling},
        "failures": failures,
        "failures_across_probes": sum(1 for probe in probes if probe.get("error")),
        "probes": probes,
    }


def print_report(report: dict[str, Any]) -> None:
    tq4 = report["tq4"]
    timed = len(tq4["elapsed_ms"])
    print("TQ4 / NFR-01 - latency at ~800 characters")
    if tq4["p95_ms"] is None:
        print("  No timing recorded (every sample came from cache or failed).")
    else:
        for chars, elapsed in zip(tq4["char_counts"], tq4["elapsed_ms"]):
            print(f"  {chars} chars: {elapsed} ms")
        print(
            f"  median {tq4['median_ms']} ms, "
            f"p95 (slowest of {timed}) {tq4['p95_ms']} ms"
        )
        verdict = "PASS" if tq4["within_target"] else "FAIL"
        print(f"  target <= {report['targets']['nfr_01_ms']} ms p95: {verdict}")

    print("TQ5 - length ceiling")
    for probe in report["tq5"]["probes"]:
        print(f"  {probe['char_count']} chars: {_outcome_text(probe)}")

    print("\nMarkdown for TRD section 20 / NFR-01")
    if tq4["p95_ms"] is None:
        print("| (no TQ4 timing recorded this run) | |")
    else:
        print(f"| Method | {timed} distinct scripts of 780-800 characters |")
        print(f"| Median | {tq4['median_ms']} ms |")
        print(f"| p95 (slowest of {timed}) | {tq4['p95_ms']} ms |")
    for probe in report["tq5"]["probes"]:
        print(f"| {probe['char_count']} characters | {_outcome_text(probe)} |")


if __name__ == "__main__":
    sys.exit(main())
