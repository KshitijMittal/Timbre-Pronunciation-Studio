"""Milestone 3 - Gate B pronunciation POC.

For each curated term this script writes two WAVs with identical model, voice,
language and speed: the sentence as written, and the sentence with the authored
respelling applied by the real rule engine.

Usage (from the project root):
    .venv/Scripts/python.exe scripts/poc_matrix.py --dry-run   # no key, no credits
    .venv/Scripts/python.exe scripts/poc_matrix.py             # 16 API calls

The rule engine is imported from the backend package on purpose: the POC must
test the same matching semantics the product ships, not a reimplementation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
AUDIO_DIR = PROJECT_ROOT / "data" / "audio"
RESULTS_JSON = PROJECT_ROOT / "data" / "poc_results.json"
RESULTS_MD = PROJECT_ROOT / "data" / "poc_results.md"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from _guard import confirm_credit_spend, load_api_key  # noqa: E402
from app.core.pronunciation_rules import Rule, apply_rules  # noqa: E402

AUDIO_CONFIG = {
    "sample_rate": 48000,
    "num_channels": 1,
    "sample_width": 2,
    "encoding": "linear_pcm",
    "container": "wav",
}

# Fixed for every pair. Changing any of these invalidates the comparison.
SETTINGS = {
    "model": "timbre-v3.0",
    "voice": "Lakshmi",
    "language": "en-IN",
    "speed": 1.0,
}

TERMS = [
    {
        "category": "Invented brand",
        "term": "Zentara",
        "intended": "zen-TAA-ra",
        "respelling": "Zen Taara",
        "sentence": "We shipped Zentara to every customer on the same day.",
    },
    {
        "category": "Invented brand",
        "term": "Nuvora",
        "intended": "noo-VOH-ra",
        "respelling": "Noovora",
        "sentence": "Nuvora is the name of the new analytics product.",
    },
    {
        "category": "Indian personal name",
        "term": "Aniruddh",
        "intended": "uh-ni-ROODH",
        "respelling": "Aniroodh",
        "sentence": "Aniruddh will present the roadmap on Friday morning.",
    },
    {
        "category": "Indian personal name",
        "term": "Shreyas",
        "intended": "SHRAY-us",
        "respelling": "Shrayas",
        "sentence": "Shreyas joined the platform team last month.",
    },
    {
        "category": "Place name",
        "term": "Bengaluru",
        "intended": "ben-ga-LOO-roo",
        "respelling": "Bengalooru",
        "sentence": "The Bengaluru office opens at nine in the morning.",
    },
    {
        "category": "Acronym read as a word",
        "term": "NABARD",
        "intended": "NAA-bard, not N-A-B-A-R-D",
        "respelling": "Naabard",
        "sentence": "NABARD published its annual report for rural lending.",
    },
    {
        "category": "Technical term",
        "term": "Kubernetes",
        "intended": "koo-ber-NET-eez",
        "respelling": "Kubernetees",
        "sentence": "The cluster runs on Kubernetes with autoscaling enabled.",
    },
    {
        "category": "Product name",
        "term": "Timbre",
        "intended": "TAM-ber",
        "respelling": "Tamber",
        "sentence": "Timbre speaks Indian languages clearly and naturally.",
    },
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def synthesize(*, api_key: str, base_url: str, text: str) -> tuple[int, bytes, int, dict | None]:
    started = time.perf_counter()
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/v1/tts/inference",
            headers={
                "Content-Type": "application/json",
                "X-API-Key-ID": api_key,
            },
            json={
                "text": text,
                "model": SETTINGS["model"],
                "voice": SETTINGS["voice"],
                "language": SETTINGS["language"],
                "speed": SETTINGS["speed"],
                "audio_config": AUDIO_CONFIG,
            },
            timeout=120.0,
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 0, b"", elapsed_ms, {"type": type(exc).__name__, "message": str(exc)}

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code == 200 and response.content:
        return response.status_code, response.content, elapsed_ms, None
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
    except ValueError:
        error = {"type": f"HTTP_{response.status_code}", "message": response.text[:200]}
    return response.status_code, b"", elapsed_ms, error


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate B pronunciation POC matrix")
    parser.add_argument("--dry-run", action="store_true", help="compute transforms only")
    parser.add_argument(
        "--confirm-spend",
        action="store_true",
        help="skip the typed credit confirmation (only with the user's explicit go-ahead)",
    )
    parser.add_argument("--model", default=SETTINGS["model"])
    parser.add_argument("--voice", default=SETTINGS["voice"])
    parser.add_argument("--speed", type=float, default=SETTINGS["speed"])
    args = parser.parse_args()

    if args.dry_run:
        print("Dry run: no API calls, no credits spent.\n")
    else:
        SETTINGS.update(model=args.model, voice=args.voice, speed=args.speed)
        if args.confirm_spend:
            print(f"Confirmed in advance: up to {len(TERMS) * 2} paid call(s).")
        else:
            confirm_credit_spend(
                len(TERMS) * 2,
                detail="Two calls per term: the original sentence and the adjusted one.",
            )

    api_key = "" if args.dry_run else load_api_key()
    base_url = os.getenv("GNANI_BASE_URL", "https://api.vachana.ai")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Settings held constant for every pair: {SETTINGS}\n")

    results = []
    failures = 0

    for index, item in enumerate(TERMS, start=1):
        rule = Rule(source=item["term"], replacement=item["respelling"], rule_id=f"poc{index}")
        transformed = apply_rules(item["sentence"], [rule])
        changed = transformed.transformed_text != item["sentence"]

        stem = f"poc_{index:02d}_{slug(item['term'])}"
        record = {
            "index": index,
            "category": item["category"],
            "term": item["term"],
            "intended": item["intended"],
            "respelling": item["respelling"],
            "sentence": item["sentence"],
            "transformed_text": transformed.transformed_text,
            "matches": transformed.matches[0].count,
            "changed": changed,
            "settings": dict(SETTINGS),
            "original_file": f"{stem}_original.wav",
            "adjusted_file": f"{stem}_adjusted.wav",
            "original_status": None,
            "adjusted_status": None,
            "verdict": "pending",
            "notes": "",
        }

        print(f"[{index}/8] {item['category']}: {item['term']} -> {item['respelling']}")
        print(f"  changed: {changed}, matches: {record['matches']}")
        if not changed:
            print("  WARNING: the rule did not match the sentence. Fix the sentence or term.")

        if not args.dry_run:
            print("  generating original ...")
            status, audio, elapsed, error = synthesize(
                api_key=api_key, base_url=base_url, text=item["sentence"]
            )
            record["original_status"] = status
            if audio:
                (AUDIO_DIR / record["original_file"]).write_bytes(audio)
                print(f"    saved {record['original_file']} ({len(audio):,} bytes, {elapsed} ms)")
            else:
                failures += 1
                print(f"    FAILED: HTTP {status} {error}")

            print("  generating adjusted ...")
            status, audio, elapsed, error = synthesize(
                api_key=api_key, base_url=base_url, text=transformed.transformed_text
            )
            record["adjusted_status"] = status
            if audio:
                (AUDIO_DIR / record["adjusted_file"]).write_bytes(audio)
                print(f"    saved {record['adjusted_file']} ({len(audio):,} bytes, {elapsed} ms)")
            else:
                failures += 1
                print(f"    FAILED: HTTP {status} {error}")

        results.append(record)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dry_run": args.dry_run,
        "settings": dict(SETTINGS),
        "audio_config": AUDIO_CONFIG,
        "gate_b": {
            "threshold_improved": 6,
            "improved": None,
            "collateral_damage": None,
            "result": "pending human listening",
        },
        "terms": results,
    }
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Gate B pronunciation POC results",
        "",
        f"Generated: {payload['generated_at']}",
        f"Settings: {SETTINGS}",
        "",
        "| # | Category | Term | Respelling | Intended | Verdict | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in results:
        lines.append(
            f"| {record['index']} | {record['category']} | {record['term']} | "
            f"{record['respelling']} | {record['intended']} | {record['verdict']} | "
            f"{record['notes']} |"
        )
    lines += [
        "",
        "Verdict values: closer / no change / worse / damaged the sentence.",
        "Gate B passes at 6 or more \"closer\" with zero collateral damage.",
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nWrote {RESULTS_JSON}")
    print(f"Wrote {RESULTS_MD}")
    if args.dry_run:
        print("\nNext: run without --dry-run to generate the 16 WAVs.")
    else:
        print(
            "\nNext: listen to each pair in order, fill in `verdict` and `notes` in "
            "poc_results.json, then record the Gate B decision."
        )
    if failures:
        print(f"\n{failures} generation(s) failed - the POC is incomplete.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
