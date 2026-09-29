# Evaluation harness

This is a **synthetic** dataset. Run `python generate_scenarios.py --seed 8042 --reference-date 2026-09-28` from this folder to regenerate 80 scenarios. `datasets/requests.jsonl` is the only file submitted to `/plan`; `datasets/ground_truth.jsonl` is opened locally by the runner after each response. Do not add the label file to the AI template index or a model prompt.

Start the AI service, set `INTERNAL_KEY` in the environment, then run `python run_planning.py --base-url http://localhost:8001 --split development`. Freeze changes before running `--split held_out`. This writes JSON counts and per-case results to `results/`; any missing response makes the run incomplete and suppresses aggregate metrics.

The planning runner does **not** execute n8n or evaluate reminders/recovery. Those labels are held for triggered integration tests. See `../docs/EVALUATION.md` for acceptance thresholds, evidence requirements and current limits. `results/REPORT.md` is the human-readable status record until a complete run creates a dated result report.

## After changing the extractor

The original held-out failures have been inspected, so the original 55 cases are development diagnostics for any subsequent change. Have an independent reviewer who has **not** read the old labels/misses author a JSON object mapping each `service:key` feature to a list of fresh phrases. Use new entities and later dates, and keep the new set in a new directory:

```text
python evals/generate_scenarios.py --seed 9127 --reference-date 2027-01-15 --held-out-phrases path/to/new-phrases.json --id-prefix CL-FRESH --entity-prefix Fresh Client --output-dir evals/datasets/fresh-2027-01
python evals/run_local_demo.py --dataset-dir evals/datasets/fresh-2027-01 --result-prefix fresh_2027_01
```

This repository does not supply a fresh phrase bank, because authoring it from inspected misses would contaminate the next held-out evaluation. The resulting labels must stay outside runtime prompts/template retrieval. A newly scored set is a new experiment, not a retroactive repair of `planning_held_out_demo.json`.
