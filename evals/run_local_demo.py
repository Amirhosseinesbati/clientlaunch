"""Run the actual AI FastAPI /plan route in-process in DEMO mode.

This needs the project's Python dependencies, but no Docker or provider key.
It evaluates deterministic fixtures only; it does not exercise n8n.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from run_planning import score


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
os.environ["MODEL_MODE"] = "demo"
os.environ["INTERNAL_KEY"] = secrets.token_hex(24)
os.environ.pop("AI_CHECKPOINT_DSN", None)

from apps.ai.main import app  # noqa: E402 - mode and key must precede import


def fmt(value: float | None) -> str:
    return "not scored" if value is None else f"{value:.1%}"


def fraction(result: dict, numerator: str, denominator_extra: str, metric: str) -> str:
    counts = result["counts"]
    n = counts.get(numerator, 0)
    d = n + counts.get(denominator_extra, 0)
    return f"{n}/{d} ({fmt(result[metric])})"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "datasets")
    parser.add_argument("--result-prefix", default="planning")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    summaries = []
    with TestClient(app) as client:
        def request_plan(payload: dict) -> dict:
            response = client.post("/plan", json=payload, headers={"X-Internal-Key": os.environ["INTERNAL_KEY"]})
            response.raise_for_status()
            return response.json()

        for split in ("development", "held_out"):
            result = score("in-process", os.environ["INTERNAL_KEY"], split, 30.0, request_plan,
                           dataset_dir=args.dataset_dir)
            output = args.output_dir / f"{args.result_prefix}_{split}_demo.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            summaries.append((split, result, output.name))
            print(f"{split}: {result['status']} {result['responded']}/{result['attempted']}; "
                  f"precision={fmt(result['scope_precision'])}; required recall={fmt(result['required_input_recall'])}")

    lines = [
        "# Deterministic demo fixture evaluation",
        "",
        f"Run date (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
        "",
        "The actual FastAPI `/plan` route and LangGraph demo extractor were called in process. "
        "These synthetic fixture scores do not establish connected-model quality, n8n execution, "
        "provider behavior or customer accuracy.",
        "",
        "| Split | Completed calls | Scope precision | Scope recall diagnostic | Required-input recall | Result file |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for split, result, output in summaries:
        lines.append(f"| {split} | {result['responded']}/{result['attempted']} "
                     f"| {fraction(result, 'scope_tp', 'scope_fp', 'scope_precision')} "
                     f"| {fraction(result, 'scope_tp', 'scope_fn', 'scope_recall_diagnostic')} "
                     f"| {fraction(result, 'required_tp', 'required_fn', 'required_input_recall')} | `{output}` |")
    held_out = next(result for split, result, _ in summaries if split == "held_out")
    target_met = (held_out["scope_precision"] is not None and held_out["scope_precision"] >= 0.95
                  and held_out["required_input_recall"] is not None and held_out["required_input_recall"] >= 0.90)
    lines.extend(["", f"The held-out DEMO fixture target was {'met' if target_met else 'not met'}. "
                  "Once inspected, this set must not be reused as unbiased post-fix evidence. "
                  "Runtime n8n journeys, browser screenshots and connected-model tests remain pending.", ""])
    report_name = "REPORT.md" if args.result_prefix == "planning" else f"{args.result_prefix}_REPORT.md"
    (args.output_dir / report_name).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
