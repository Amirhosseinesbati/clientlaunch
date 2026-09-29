"""Score actual /plan responses against synthetic scenario labels.

No score is written when the service cannot be reached or any response fails.
This runner does not claim to test n8n, reminder scheduling or recovery.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent
TEMPLATE_KEYS = {
    entry["service_code"]: {task["key"] for task in entry["tasks"]}
    for entry in json.loads((ROOT.parent / "apps" / "ai" / "templates.json").read_text(encoding="utf-8"))
}


def ontology_item_key(item: dict) -> str:
    service = item.get("service_code", "")
    key = item.get("key", "")
    prefix = service + "_"
    if item.get("source") == "scope" and key.startswith(prefix):
        key = key[len(prefix):]
    elif item.get("source") == "template" and key not in TEMPLATE_KEYS.get(service, set()):
        # Earlier graph versions prefixed template keys. The catalog resolves
        # that legacy spelling without stripping legitimate keys such as
        # `website_copy` or `content_approver`.
        if key.startswith(prefix) and key[len(prefix):] in TEMPLATE_KEYS.get(service, set()):
            key = key[len(prefix):]
    return f"{service}:{key}"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score(
    base_url: str,
    key: str,
    split: str,
    timeout: float,
    request_plan: Callable[[dict], dict] | None = None,
    dataset_dir: Path = ROOT / "datasets",
) -> dict:
    requests = [r for r in read_jsonl(dataset_dir / "requests.jsonl") if r["split"] == split]
    labels = {r["scenario_id"]: r for r in read_jsonl(dataset_dir / "ground_truth.jsonl")}
    counts: Counter[str] = Counter()
    per_case: list[dict] = []
    mode: str | None = None
    for scenario in requests:
        scenario_id = scenario["scenario_id"]
        try:
            if request_plan is not None:
                result = request_plan(scenario["request"])
            else:
                body = json.dumps(scenario["request"]).encode("utf-8")
                request = urllib.request.Request(
                    base_url.rstrip("/") + "/plan", data=body, method="POST",
                    headers={"Content-Type": "application/json", "X-Internal-Key": key},
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    result = json.load(response)
        except Exception as exc:
            per_case.append({"scenario_id": scenario_id, "error": str(exc)})
            continue
        if mode is None:
            mode = result.get("model_mode")
        elif result.get("model_mode") != mode:
            per_case.append({"scenario_id": scenario_id, "error": "model_mode changed during run"})
            continue
        returned = result.get("checklist", [])
        if not isinstance(returned, list):
            per_case.append({"scenario_id": scenario_id, "error": "checklist response is not a list"})
            continue
        predicted_scope = {ontology_item_key(item) for item in returned if item.get("source") == "scope"}
        predicted_all = {ontology_item_key(item) for item in returned if item.get("required")}
        expected_scope = set(labels[scenario_id]["expected_scope_items"])
        expected_required = set(labels[scenario_id]["expected_required_inputs"])
        tp = len(predicted_scope & expected_scope)
        fp = len(predicted_scope - expected_scope)
        scope_fn = len(expected_scope - predicted_scope)
        fn = len(expected_required - predicted_all)
        counts.update({"scope_tp": tp, "scope_fp": fp, "scope_fn": scope_fn,
                       "required_tp": len(predicted_all & expected_required), "required_fn": fn})
        per_case.append({"scenario_id": scenario_id, "scope_tp": tp, "scope_fp": fp, "scope_fn": scope_fn,
                         "required_missing": sorted(expected_required - predicted_all),
                         "extra_scope": sorted(predicted_scope - expected_scope)})
    errors = [item for item in per_case if "error" in item]
    status = "complete" if not errors and len(per_case) == len(requests) else "incomplete"
    p_den = counts["scope_tp"] + counts["scope_fp"]
    sr_den = counts["scope_tp"] + counts["scope_fn"]
    r_den = counts["required_tp"] + counts["required_fn"]
    return {
        "status": status, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "actual /plan route responses" if request_plan else "actual /plan HTTP responses",
        "split": split, "mode": mode, "dataset_dir": str(dataset_dir),
        "attempted": len(requests), "responded": len(per_case) - len(errors),
        "errors": errors, "counts": dict(counts),
        "scope_precision": counts["scope_tp"] / p_den if status == "complete" and p_den else None,
        "scope_recall_diagnostic": counts["scope_tp"] / sr_den if status == "complete" and sr_den else None,
        "required_input_recall": counts["required_tp"] / r_den if status == "complete" and r_den else None,
        "per_case": per_case,
        "not_scored": ["reminder decisions", "recovery outcomes", "connected Drive/Trello/SMTP", "n8n triggered executions"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("AI_BASE_URL", "http://localhost:8001"))
    parser.add_argument("--internal-key", default=os.getenv("INTERNAL_KEY"))
    parser.add_argument("--split", choices=("development", "held_out"), default="held_out")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "datasets")
    parser.add_argument("--result-prefix", default="planning")
    args = parser.parse_args()
    if not args.internal_key:
        parser.error("Set INTERNAL_KEY or pass --internal-key")
    result = score(args.base_url, args.internal_key, args.split, args.timeout, dataset_dir=args.dataset_dir)
    out = ROOT / "results" / f"{args.result_prefix}_{args.split}_{result['mode'] or 'unavailable'}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{result['status']}: {result['responded']}/{result['attempted']} actual responses; {out}")
    if result["status"] != "complete":
        sys.exit(1)


if __name__ == "__main__":
    main()
