# ClientLaunch handover

**As of:** 2026-09-28. This is an independent portfolio pilot with synthetic data. Docker launch, signed n8n intake/replay, exact user-authorized approval, forced board failure/recovery and five synthetic client answers passed local checks. The logo upload, handoff and connected-provider journey has **not** passed runtime acceptance. Do not represent this as a customer deployment.

## Launch

From `/path/to/clientlaunch` after starting Docker Desktop/Engine with Compose:

```powershell
node scripts/demo.mjs
```

The same command works in a POSIX shell with Node.js and Docker Compose installed. It creates an ignored `.env` with local random secrets on first run, starts the Compose services, applies API migrations, runs the full synthetic seed, and invokes `scripts/bootstrap_n8n.mjs` with `--publish-demo --enable-demo-schedule` **only when `CONNECTOR_MODE=demo`**. Plain `node scripts/bootstrap_n8n.mjs` imports and verifies IDs while leaving workflows unpublished. The launcher builds Compose images sequentially. This sequence completed locally: five services started, migration `0003` and the full PostgreSQL seed loaded. Docker Desktop briefly went offline, then recovered; a ten-workflow/94-node pack was reimported/published and five webhook routes registered. The latest 96-node source pack passed static validation but has not been reimported because Docker overlayfs returned an I/O error. If a later run fails, inspect `docker compose logs api ai n8n db web` and do not infer later steps ran.

The local URLs are portal `http://localhost:8080`, API `http://localhost:8018`, AI `http://localhost:8021` (loopback only), and n8n `http://localhost:5678`. API and n8n health returned HTTP 200 after Docker Desktop recovered; AI health and portal HTTP 200 were observed earlier. The demo operator email is `operator@northstar.example.com`. `DEMO_ADMIN_PASSWORD` is generated into ignored `.env` and printed only on first launcher run. On a fresh n8n instance, the launcher sets up owner `n8n-demo@clientlaunch.example.com` with a generated password stored in ignored `.env`. This document contains no password or real secret. These are local demo credentials, never connected-deployment defaults. The client portal is reached through an invitation link created for an approved onboarding; no shared client password is used.

To regenerate the evaluation scenario files without starting services, run `python evals/generate_scenarios.py --seed 8042 --reference-date 2026-09-28` with a Python 3.12 interpreter. To score the actual planning service, set `INTERNAL_KEY` in the environment, then run `python evals/run_planning.py --split held_out`. Its JSON result is valid only when the service responds to every scenario.

## Source inventory

| Area | Main paths | Status |
|---|---|---|
| Business state/API | `apps/api/` | 17/17 local API tests passed, including five isolated connected-startup guards, viewer token redaction, stale-delivered-dispatch safety, card concurrency and connected-board reconciliation; earlier API health and signed intake/replay passed in Compose |
| AI planning graph/adapters | `apps/ai/` | DEMO `/plan` route evaluated in process across five 80-scenario synthetic suites; AI service health passed in Compose; connected model pending |
| Operator and client web | `apps/web/` | Production Vite build, typecheck and 3/3 tests passed after handoff and connected-board recovery UI changes; preapproval, failure and recovered screenshots saved at 1440/1024/390px; browser approval click and logo upload/handoff captures pending |
| n8n workflow pack | `workflows/*.json`, `manifest.json` | Latest 10 exports / 96 nodes passed static validation but not reimported after Docker overlayfs I/O; earlier 94-node pack imported/published with 5 webhook routes and ran Drive/Trello sub-workflows; new reminder webhook/card reconciliation pending triggered checks |
| Local launcher/seed/bootstrap | `scripts/demo.mjs`, `seed.py`, `bootstrap_n8n.mjs` | One-command Docker launch, PostgreSQL migration/full seed and workflow bootstrap completed locally |
| Evaluation scenarios | `evals/datasets/` | 80 generated; structure/count verified |
| Docs/decisions | `docs/` | Launch, intake/replay, authorized approval and forced-failure/recovery evidence and remaining gates recorded after the local run |
| CI | `.github/workflows/ci.yml` | Python lock install, AI/API tests, workflow/dataset validation and web build/test configured; not run in GitHub Actions |

## Implemented / verified / pending

| Requirement | Source state | Evidence state |
|---|---|---|
| Signed won-deal intake and replay/conflict handling | API route present | Local FastAPI/SQLite tests and triggered n8n test passed: original 200, identical replay 200/same onboarding, conflicting replay 409 |
| Versioned plan and exact-hash approval | API/AI source present | Local hash/single-use test passed; user-authorized synthetic Willow Harbor Studio revision approved once and dispatched to n8n |
| Folder/board sub-workflows, frozen service-folder blueprint and idempotent operation ledger | Workflow/API/web source present | Triggered provisioning created root + 7 child folders; forced board failure then operator recovery reused folders and created one board + 6 cards. Nine provisioning operations succeeded; zero remained failed |
| Welcome/demo outbox, client intake and asset upload | API/web source present | One DEMO welcome outbox entry created in triggered Willow journey; five scoped client answers accepted in n8n executions 42–43 and five cards completed; logo asset upload pending |
| Reminder caps and paused/completed stop conditions | API/workflow source present | Local paused reminder assertion and earlier schedule publication passed; authenticated `clientlaunch/reminder-run` webhook exists only in latest 96-node export and has not been imported or triggered |
| Five-minute pending-dispatch sweep | API/workflow source present | Earlier 94-node version imported/published and orders by attempt count, records each attempt and acknowledges only a 2xx webhook. New API checks delivered triggers after five minutes and safely requeues incomplete work, excluding uncertain operations and queued welcome SMTP; local API tests passed, triggered retry pending |
| Ready/handoff evidence | API/UI source present | Persisted handoff summary/evidence and linked answers/assets/resources now appear in operator detail; API tests and frontend typecheck passed; triggered ready-to-handoff journey pending |
| Connected startup guard | API/Compose source present | Five isolated tests passed; Compose now passes `APP_MODE`, `COOKIE_SECURE`, `CORS_ORIGINS` and `docker compose config --quiet` passed. No connected container smoke test or provider credentials |
| Viewer and concurrent card safety | API/UI source present | Viewer detail hides invite link and token-bearing welcome body; card claim checks expected status/key and preserves in-flight/unknown write during client changes; connected board reconciliation needs verified To Do list ID. Targeted API tests and UI typecheck/build passed; latest container runtime pending |
| Two-workspace full synthetic seed | Seed source present | PostgreSQL full seed printed 2 workspaces, 60 clients, 90 won deals, 16 template rows / 8 types, 1,000 checklist, 250 assets, 180 submissions, 649 task cards, 30 planted failure histories; SQLite migration/seed also exercised |
| 80 evaluation scenarios | Generator and files present | **80 distinct IDs counted; 25/55 split** |
| AI scope precision ≥95%, required-input recall ≥90% | Evaluation runner present | Independent synthetic DEMO Fresh4: **35/35 = 100% precision**, **245/258 = 95.0% required-input recall** across 55/55 held-out calls; both numeric targets met for this fixture. Scope recall diagnostic 35/48 = 72.9%. Connected model and real proposal review pending |
| Connected Google Drive/Trello/SMTP/model | Configuration path intended | Credential setup and authorized smoke tests pending |
| Restore, backup and visual widths/screenshots | Runbooks present | Earlier business and n8n database dumps restored into temporary isolated databases with matching core counts, before migration `0003` and tenth workflow import; preapproval/failure/recovery screenshots saved under `screenshots/`; latest-schema/service/asset/credential restore pending |

The latest Willow recovery path ran as n8n executions 37–40 and ended in `waiting_for_client`; the corresponding forced board failure and Error Trigger runs were also observed. A complete client handoff, live-model score, latency number or customer outcome has not been verified. Local DEMO screenshots are linked from [PORTFOLIO.md](PORTFOLIO.md). The current directory is **not a Git repository**, so there is no current commit hash to report and `.github/workflows/ci.yml` has not run on a remote. If the project is placed under Git, record the commit here and keep generated `.env`/runtime secrets ignored.

**UI approval gate:** An earlier browser QA attempt to approve a different seeded QA client was rejected by automatic approval review because it could trigger provisioning; that action was not retried through the API. The user subsequently gave explicit authorization for the synthetic Willow Harbor Studio plan, onboarding `612b4755-1234-4640-8c9b-1781417691ab`. After Docker Desktop recovered, its approval executed once through the local operator API, and downstream n8n provisioning/recovery ran. A separate approval route test passed in an isolated disposable SQLite test database. A browser click-through for the Willow approval was not separately recorded.

## Immediate next actions

1. Recover Docker overlayfs/storage health, reimport the 96-node export and verify its routes. Continue from Willow Harbor Studio `waiting_for_client`: upload the remaining synthetic logo asset, verify its card sync/readiness and record a factual handoff with persisted detail and links. Five other answers/cards already completed. Save redacted execution IDs and relevant business rows.
2. Exercise a due reminder, pending-dispatch retry/fairness, ambiguous timeout/reconciliation, stale/expired portal link and cross-workspace isolation. The forced board-failure/recovery path is already recorded; do not count it as evidence for all failure modes.
3. Review the saved 1440/1024/390-pixel captures in [PORTFOLIO.md](PORTFOLIO.md), add client-intake/handoff states and check keyboard/focus/overflow and contrast.
4. Preserve the Fresh4 fixture result in `fresh4_output/results/`. Original, Fresh, Fresh2 and Fresh3 are historical debugging sets; if the extractor changes again, author another independent held-out set. Evaluate connected mode only with authorized credentials and a spending cap, and human-review model evidence on permitted real proposals.
5. Extend the database-only restore smoke test to services, assets and encrypted credentials; record retention, provider ownership and n8n license position before a real customer pilot. n8n 2.40.7 emitted a PostgreSQL 16 compatibility warning; assess and test PostgreSQL 17 for customer installation.

For customer-specific setup, see [OPERATIONS.md](OPERATIONS.md), [SECURITY.md](SECURITY.md) and [COMMERCIALIZATION.md](COMMERCIALIZATION.md).
