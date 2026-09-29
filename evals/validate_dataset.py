"""Validate separation and structure of a synthetic evaluation dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    requests = read_jsonl(directory / "requests.jsonl")
    labels = read_jsonl(directory / "ground_truth.jsonl")
    request_ids = [row["scenario_id"] for row in requests]
    label_ids = [row["scenario_id"] for row in labels]
    if len(request_ids) != len(set(request_ids)) or len(label_ids) != len(set(label_ids)):
        raise ValueError("Scenario IDs must be unique within each file")
    if set(request_ids) != set(label_ids):
        raise ValueError("Request and label IDs differ")
    if len(requests) != manifest["count"] or len(labels) != manifest["count"]:
        raise ValueError("Dataset counts differ from manifest")
    split_counts = Counter(row["split"] for row in requests)
    if split_counts != Counter({"development": manifest["development"], "held_out": manifest["held_out"]}):
        raise ValueError("Split counts differ from manifest")
    label_map = {row["scenario_id"]: row for row in labels}
    for row in requests:
        if row["split"] != label_map[row["scenario_id"]]["split"]:
            raise ValueError(f"Split differs for {row['scenario_id']}")
        if set(row) != {"scenario_id", "split", "request"}:
            raise ValueError(f"Runtime request row contains unexpected fields: {row['scenario_id']}")
        if "expected_" in json.dumps(row):
            raise ValueError(f"Ground-truth marker leaked into request: {row['scenario_id']}")
        purchased = row["request"]["purchased_services"]
        if not purchased or len(purchased) != len(set(purchased)):
            raise ValueError(f"Invalid purchased services for {row['scenario_id']}")
        answer = label_map[row["scenario_id"]]
        if not set(answer["expected_scope_items"]).issubset(answer["expected_required_inputs"]):
            raise ValueError(f"Scope labels are missing from required labels for {row['scenario_id']}")
        if any(key.split(":", 1)[0] not in purchased for key in answer["expected_required_inputs"]):
            raise ValueError(f"Required label uses unpurchased service: {row['scenario_id']}")
    return {"count": len(requests), "development": split_counts["development"], "held_out": split_counts["held_out"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "datasets")
    args = parser.parse_args()
    print(json.dumps(validate(args.dataset_dir), indent=2))


if __name__ == "__main__":
    main()
