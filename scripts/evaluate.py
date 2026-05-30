#!/usr/bin/env python3
"""Evaluate detection on a folder of labeled clips (filename convention)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import get_settings
from core.processor import AccidentDetectionProcessor
from media.video_reader import VideoSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate TADS on labeled clips")
    parser.add_argument("--dir", required=True, help="Directory with .mp4 files")
    parser.add_argument("--labels", required=True, help="JSON labels: {filename: true/false}")
    args = parser.parse_args()

    clip_dir = Path(args.dir)
    with Path(args.labels).open(encoding="utf-8") as f:
        labels: dict[str, bool] = json.load(f)

    processor = AccidentDetectionProcessor(settings=get_settings())
    tp = fp = tn = fn = 0
    results = []

    for name, is_incident in labels.items():
        path = clip_dir / name
        if not path.exists():
            print(f"SKIP missing: {name}")
            continue
        result = processor.process_source(VideoSource.from_file(path))
        detected = len(result.incidents) > 0
        results.append({"file": name, "expected": is_incident, "detected": detected, "count": len(result.incidents)})

        if is_incident and detected:
            tp += 1
        elif is_incident and not detected:
            fn += 1
        elif not is_incident and detected:
            fp += 1
        else:
            tn += 1

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-6)

    report = {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "clips": results,
    }
    print(json.dumps(report, indent=2))

    out = get_settings().resolve_path("output/eval_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
