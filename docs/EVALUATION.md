# Evaluation and verification record

**Record date:** 2026-09-28. Release status: **incomplete**. Signed intake, exact approval, forced board failure/recovery and a five-answer client submission have run through local n8n, and browser captures were saved. Logo upload, handoff, reminder/sweep behavior, full restore and connected-provider checks remain. The synthetic DEMO planning metrics below do not establish connected-model or customer accuracy.

## Evidence currently available

| Check | Command / method | Observed result | Scope |
|---|---|---|---|
| Evaluation dataset generation | Bundled Python `evals/generate_scenarios.py` | 80 distinct request IDs and 80 labels; 25 development, 55 held out | Dataset structure only |
| Evaluation scripts syntax | Bundled Python `-m py_compile evals/generate_scenarios.py evals/run_planning.py` | Completed without error | Syntax only |
| AI deterministic fixture evaluation | `.venv\\Scripts\\python.exe evals\\run_local_demo.py` using FastAPI `TestClient` and the actual `/plan` route | Five 80-scenario suites completed; Fresh4 result in `fresh4_output/results/` | DEMO fixture only |
| AI unit tests | `.venv\\Scripts\\python.exe -m unittest discover -s tests\\ai -v` | **6/6 passed** | Local deterministic service checks; no connected model |
| SQLite migration and full seed | `.venv\\Scripts\\alembic.exe -c apps\\api\\alembic.ini upgrade head`; `.venv\\Scripts\\python.exe -m scripts.seed --mode fast` then `--mode full` with isolated SQLite URL | `0001_initial → 0002_task_cards` passed; full printed 2 workspaces, 60 clients, 90 deals, 16 template rows (8 types × 2), 1,000 checklist, 250 assets, 180 submissions, 649 synced synthetic board cards, 30 partial-failure operations | Local SQLite, not PostgreSQL |
| Backend route tests | `.venv\\Scripts\\python.exe -m unittest discover -s tests\\api -v` | **17/17 passed**, including five isolated connected-startup checks, viewer token redaction, stale-delivered-dispatch safety, card concurrency and connected-board reconciliation | FastAPI/SQLite and isolated startup tests; no new n8n trigger |
| Workflow static validation and Compose parse | `python scripts/validate_workflows.py`; `docker compose config --quiet` | **10 workflow exports / 96 nodes** passed latest static validation; Compose config parsed after API environment passthrough | Earlier 94-node pack imported/published; latest 96-node source not reimported due Docker overlayfs I/O |
| Evaluation dataset structure | `.venv\\Scripts\\python.exe evals\\validate_dataset.py` | 80 matching unique request/label IDs; 25/55 split; no answer fields in runtime input | Structure only |
| Web type/build/unit checks | `pnpm build`, `pnpm test`, TypeScript typecheck in `apps/web` | Latest production Vite build and typecheck passed after connected-board UI change; **3/3 API-boundary tests passed** | Local frontend checks, no CI run or refreshed browser handoff |
| Workflow files | JSON parse, static validator and n8n bootstrap | Ten workflow exports and manifest parse; 96-node source validates, 94-node pack previously imported/published | Latest source has not run in n8n |
| AI service | Python syntax compilation and in-process `/plan` fixture runs | Six local tests and fixture execution passed | Connected mode pending |
| Docker/n8n | `node scripts/demo.mjs`, reimport, n8n database inspection and triggered webhooks on 2026-09-28 | Five services launched, migration `0003` applied, full seed loaded; ten-workflow/94-node pack imported/published with five webhook registrations. Signed intake/replay returned 200/200/409 and invalid signature 401. The user-authorized Willow approval triggered folder work; forced board failure recovered through executions 37–40. Five client answers and matching cards completed through submission/task-sync executions 42–43. | DEMO provisioning/recovery/partial intake verified on imported 94-node pack; latest 96-node source, logo asset, handoff and schedules pending |
| Browser journeys/screenshots | Operator and client states at 1440/1024/390px; `node scripts/capture_demo.mjs --onboarding 612b4755-1234-4640-8c9b-1781417691ab --phase <label>` | Preapproval, failure and recovered captures saved under `screenshots/`, including a recovered 390px client portal. An earlier seeded QA plan click was rejected by automatic approval review; later exact Willow approval was explicitly authorized and executed through the local operator API. | **Partial**: browser approval click, client intake/handoff and final capture review remain |
| Connected model/Drive/Trello/SMTP | Credentials and authorized test accounts unavailable | No live request or side effect claimed | **Pending** |

Update this table with exact command, date, environment, exit status and artifact path after each run. A JSON parser or manual editor run cannot substitute for a triggered n8n execution.

## Scenario and metric protocol

Regenerate with `python evals/generate_scenarios.py --seed 8042 --reference-date 2026-09-28`. Start the AI service with a known `MODEL_MODE` and `INTERNAL_KEY`, then run `python evals/run_planning.py --split development` and once frozen `--split held_out`. The runner sends only `requests.jsonl` rows to the actual `/plan` HTTP endpoint. It writes `evals/results/planning_<split>_<mode>.json`, including per-case errors and numerators/denominators. A service error makes the run incomplete and suppresses aggregate precision/recall. The key belongs in an environment variable, not a committed command or result file.

For returned `source=scope` checklist items:

- **Precision:** correctly labeled scope items ÷ all returned scope items; target ≥95% on held out. Count explicit unsupported additions as false positives.
- **Required-input recall:** correctly returned required template and scope input keys ÷ all labeled required keys; target ≥90% on held out.
- **Scope recall diagnostic:** correctly returned scope items ÷ all labeled scope items. Report it alongside the two release targets so template-heavy cases cannot conceal missed personalized inputs.
- Report both mode and model ID/configuration. A deterministic demo fixture score proves only fixture behavior. It is not model quality. Connected-model scoring needs a human review sample for semantic correctness, since key matching misses useful paraphrases and misleading evidence.

Local DEMO runs on 2026-09-28 used `.venv\\Scripts\\python.exe evals\\run_local_demo.py` with a temporary internal key and no provider calls or database checkpoint. The first run used the original `evals/datasets/` files; Fresh, Fresh2 and Fresh3 used distinct dataset directories and result prefixes. The independent Fresh4 suite and its results are under `fresh4_output/` because new file creation under `evals/datasets/` and `evals/results/` was denied in the root run. The runner supports `--output-dir`. Results:

| Split | Actual `/plan` responses | Scope precision | Scope recall diagnostic | Required-input recall |
|---|---:|---:|---:|---:|
| Original development | 25/25 | 22/22 = 100% | 22/22 = 100% | 122/122 = 100% |
| Original held out | 55/55 | 20/20 = 100% | 20/48 = 41.7% | **230/258 = 89.1% — below the 90% target** |
| Fresh held out | 55/55 | 16/16 = 100% | 16/48 = 33.3% | **226/258 = 87.6% — below target** |
| Fresh2 held out | 55/55 | 22/23 = 95.7% | 22/48 = 45.8% | **232/258 = 89.9% — below target** |
| Fresh3 held out | 55/55 | 20/20 = 100% | 20/48 = 41.7% | **230/258 = 89.1% — below target** |
| **Fresh4 held out** | **55/55** | **35/35 = 100%** | **35/48 = 72.9%** | **245/258 = 95.0% — target met in synthetic DEMO** |

The first four held-out DEMO runs missed the **90% required-input recall target** and were inspected for debugging; **original, Fresh, Fresh2 and Fresh3 are historical development evidence**. Fresh4 was authored separately for the next evaluation and meets both specified numerical targets on synthetic DEMO fixtures. It still misses 13 of 48 personalized scope items, reflected in the 72.9% scope-recall diagnostic; this metric has no brief threshold but matters for human review. The result does not validate a connected model or real proposals. Since Fresh4 results are now visible, any later extractor tuning requires another independently authored held-out set. See `fresh4_output/results/fresh4_planning_REPORT.md` and the per-case JSON.

The requested 80 scenarios also carry reminder and recovery ground truth. They must be replayed through real API/n8n state transitions for those metrics; the current `/plan` runner marks them unscored. A later scorer correction distinguished raw template keys such as `website_copy` from prefixed legacy keys. The inspected Fresh4 set was rerun only as a regression after this contract fix and retained 35/35 precision and 245/258 required-input recall; see `fresh4_output/regression_after_contract_fix_v2/`. It is not a new independent holdout. Redacted n8n execution IDs and database state for the local intake/restore checks are in [RUNTIME_ACCEPTANCE.md](RUNTIME_ACCEPTANCE.md).

## Required acceptance matrix

| Journey / invariant | Minimum evidence | Current status |
|---|---|
| Signed won-deal → plan → exact approval → root and purchased-service child folders + board → welcome → client intake → ready handoff | Triggered n8n execution, API state, operator walkthrough | Willow approval, root + 7 child folders, board + 6 cards and welcome outbox verified after forced failure/recovery; five client answers/cards completed; logo asset and handoff pending |
| Duplicate event same payload; conflict same ID | API response and single onboarding row | Passed through n8n webhook in local DEMO |
| Timeout after folder write, uncertain response, reconciliation, one folder/board | Triggered execution plus ledger/resource rows | Pending runtime |
| Failure after folder before board; restart/recovery | Triggered execution after failure, stable external IDs | Forced DEMO board failure left root + 7 child folders, then operator recovery retried board and reached `waiting_for_client`; a same-run ID comparison and restart during the failure were not recorded |
| Reminder caps, timezone, completed/paused stop conditions | Deterministic API tests and scheduled trigger | Pending runtime |
| Connected startup guard | Isolated import with weak, repeated and valid settings; connected container startup | Five isolated tests passed; Compose config parsed after env passthrough; connected container startup pending |
| Handoff detail persistence and UI links | API detail, typed UI and recorded ready-to-handoff journey | Source and typecheck passed; live logo completion and handoff pending |
| Pending approval/submission/recovery dispatch replay | Scheduled n8n execution, 2xx acknowledgment, failed-row retry and fair 20-row batch | Earlier 94-node workflow imported/published; new five-minute stale-delivery safety check passed API tests, but source update and scheduled failed-row retry have no n8n evidence |
| Stale/expired portal link and malformed intake | 4xx response without state change | Pending runtime |
| Cross-workspace operator/client/file isolation | Authenticated negative tests | Pending runtime |
| Clean instance n8n import and sub-workflow reference mapping | Import log plus editor/execution record | Earlier 10-workflow/94-node pack imported/published with five webhook registrations; Drive and Trello sub-workflows executed during Willow provisioning/recovery. Latest 96-node pack not imported after Docker overlayfs I/O error |
| Five actual triggered scenarios | Five redacted execution IDs with outcomes | Signed intake/replay, invalid-signature rejection, forced board failure and recovery observed; five complete independent journeys pending |
| Browser desktop/tablet/mobile at 1440/1024/390 pixels | Real screenshots, clipped/keyboard/contrast check | Saved preapproval/failure/recovered captures at all three widths; keyboard/contrast and client intake/handoff captures pending |
| Database migration, restore smoke test, lint/type/build/tests/CI | PostgreSQL migration `0003`, historical isolated dump/restore of both databases with matching core counts, 17 API tests, 6 AI tests, 3 web tests, latest frontend typecheck/build, 10-workflow/96-node static check and Compose parse passed; latest-schema/service/asset/credential restore and GitHub Actions pending | Partial |

## Failure policy

Record an unresolved failure with reproduction steps and its affected release gate. Do not lower precision/recall targets silently. A failed live connector must remain failed or uncertain; it cannot fall back to a demo success. Do not call the installation production ready merely because deterministic tests pass.

## Machine-readable record

`evals/results/status.json` summarizes the historical DEMO planning suites; [RUNTIME_ACCEPTANCE.md](RUNTIME_ACCEPTANCE.md) records subsequent n8n and database checks. Fresh4's original machine-readable result is `fresh4_output/results/fresh4_planning_held_out_demo.json`; the same-set post-contract regression is separate under `fresh4_output/regression_after_contract_fix_v2/`. Generated result files are evidence only after the runner completes against a declared service mode. Do not edit an aggregate score by hand.
