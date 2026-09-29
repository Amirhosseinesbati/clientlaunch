# Operations runbook

**Scope:** customer-specific pilot installation. Commands and configuration must be checked against the current `README.md`, `compose.yaml`, `.env.example`, and `scripts/` at launch time. The local Docker launch, n8n signed intake/replay, exact DEMO approval, forced board failure/recovery and a five-answer client submission were validated on 2026-09-28. A database-only restore also passed; restored services, assets, credentials, logo upload/handoff and connected-provider behavior remain unverified.

## Local demo

Prerequisites: Docker Desktop or Docker Engine with Compose, Node.js for the launcher, free local ports declared by Compose, and enough storage for PostgreSQL, n8n data and assets. In PowerShell or a POSIX shell, from the project root:

```text
node scripts/demo.mjs
```

The launcher creates an ignored `.env` with generated demo secrets, starts PostgreSQL, n8n 2.40.7, the API, AI service and web app, seeds the demo, and prints the generated operator password once. On a fresh n8n instance it sets up owner `n8n-demo@clientlaunch.example.com`; that password is stored only in the ignored `.env`. In DEMO connector mode only, it invokes the bootstrap with `--publish-demo --enable-demo-schedule` to publish demo workflows and enable the reminder and five-minute pending-dispatch schedules. The source orders pending rows by attempt count, then creation time, processes at most 20 per run, records each attempt, and leaves a non-2xx response pending. It also checks deliveries older than five minutes against business state and requeues only safe incomplete work. Compose builds run sequentially to limit load. The command completed locally on 2026-09-28: five services were up, migration `0003` and the full PostgreSQL seed loaded. After a brief Docker Desktop interruption, a ten-workflow/94-node pack was reimported/published and five webhook routes registered; API and n8n health returned HTTP 200. The latest ten-workflow/96-node source pack passed static validation but **has not** been reimported because Docker overlayfs returned an I/O error. For manual data generation after the services are configured: `python -m scripts.seed --mode fast` or `python -m scripts.seed --mode full`. The acceptance set requires `full`.

After launch, `node scripts/replay_won_deal.mjs --case website-002 --repeat` sends a signed synthetic website deal through the n8n webhook and resends identical bytes for deduplication. `--conflict` also resends that event ID with changed scope to exercise rejection. A Python equivalent is available. The replay utility accepts only a loopback HTTP URL. This intake/replay path ran through n8n locally: original and identical replay returned HTTP 200 with the same onboarding; altered scope returned HTTP 409. To stage a one-shot board failure before an authorized test execution, call the DEMO-only `POST /sim/faults/next` internal route with `{onboarding_id,system:"trello",kind:"failure"}`; inspect the resulting operation ledger and recovery state. The authorized Willow Harbor Studio test used this fault: the board operation failed after root and seven child folders succeeded. Operator recovery retried the board only, reused folders, then created six cards and one welcome outbox item. A later scoped client batch completed five answers and their cards. Logo upload, handoff and ambiguous-timeout reconciliation remain pending.

## Environment and connector configuration

| Variable / record | Purpose | DEMO | CONNECTED |
|---|---|---|---|
| `APP_MODE`, `MODEL_MODE`, `CONNECTOR_MODE` | Mode switches | Explicit `DEMO` / `demo` | `CONNECTED` / `connected` / `connected`; API refuses mixed demo/connected modes |
| `DATABASE_URL`, n8n DB settings | Separate business and n8n persistence | Local PostgreSQL | Customer-managed PostgreSQL |
| `INTERNAL_KEY`, `WEBHOOK_SECRET`, `PORTAL_SIGNING_KEY` | Server-to-server, HMAC event and invite keys | Locally generated | Unique random values in secret store |
| `N8N_ENCRYPTION_KEY` | Decrypts n8n credentials | Locally generated and backed up | Customer-controlled protected secret |
| `COOKIE_SECURE`, `CORS_ORIGINS`, public base URLs | Browser security and links | Local-only settings | `COOKIE_SECURE=true`, HTTPS and narrow origins |
| `WEB_BASE_URL` | Base for scoped client invite links | `http://localhost:8080` | Customer HTTPS portal origin |
| `OPENAI_MODEL`, `OPENAI_API_KEY` | Connected model adapter | Not needed | Required; model ID/customer budget configured |
| Google Drive credential and root/shared-drive ID | Folder target | Simulator | Authorized customer OAuth/least-privilege root |
| Trello API credential and workspace/board policy | Task board target | Simulator | Authorized customer token |
| SMTP sender/recipients | Welcome and reminders | Local outbox only | Verified sender and authorized recipients |
| `DEMO_REFERENCE_DATE`, timezone | Deterministic dates and reminders | Fixed date | Customer timezone and real clock |
| `ASSET_STORAGE_DIR` | Scoped file storage | Local volume | Durable backed-up storage |

Credential IDs in exported JSON are placeholders. Map actual credentials on the customer instance, validate each node and inspect `workflows/manifest.json` import order. Plain `node scripts/bootstrap_n8n.mjs` imports and checks workflow IDs but leaves workflows unpublished; it does not activate a schedule. The demo launcher passes `--publish-demo --enable-demo-schedule` only when `CONNECTOR_MODE=demo`. The earlier ten-workflow/94-node pack was imported and published locally, five webhook routes registered, and Drive/Trello sub-workflows executed in the Willow Harbor Studio provisioning/recovery test. The latest 96-node export adds authenticated `POST /webhook/clientlaunch/reminder-run` and task-card reconciliation but awaits import/triggered evidence. Connected credential mapping remains pending. The provisioning workflow walks a frozen service-folder blueprint and creates child folders through the Drive sub-workflow. The five-minute sweep retries pending approval, submission and recovery dispatches and acknowledges only accepted webhooks; its actual scheduled retry behavior still needs verification. Connected schedules and external writes require customer-specific review. n8n documents [workflow import/export and the risk of credential metadata in exports](https://docs.n8n.io/build/manage-workflows/export-and-import) and [sub-workflow input contracts](https://docs.n8n.io/build/flow-logic/break-workflows-into-smaller-parts). n8n 2.40.7 emitted a PostgreSQL 16 compatibility warning during launch; evaluate and test PostgreSQL 17 before customer deployment.

`compose.yaml` now passes `APP_MODE`, `COOKIE_SECURE` and `CORS_ORIGINS` to the API, and `.env.example` declares them. `docker compose config --quiet` passed after this change; the connected container has not been started or smoke tested. Connected startup rejects missing/weak or repeated `INTERNAL_KEY` and `WEBHOOK_SECRET` values (minimum 32 characters), demo model mode, or an insecure cookie. The existing ignored DEMO `.env` uses local Compose defaults.

## Backup and restore

Back up **both** PostgreSQL databases (business and n8n), the `N8N_ENCRYPTION_KEY` / n8n user directory needed to decrypt credentials, asset storage, and the customer configuration/credential mapping record. Keep backups encrypted, access restricted and separate from the source repository. n8n documents that credentials are encrypted with a key saved in its user folder unless [a custom key is supplied](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/configuration-examples/set-a-custom-encryption-key). A database dump without that key is not a complete credential restore.

Restore smoke test procedure for an isolated environment:

1. Stop application writes and snapshot the named database and asset volumes together. Export a checksum and timestamp; do not include secrets in logs.
2. Restore into a **new** isolated instance. Set the corresponding n8n encryption key through a secret channel before starting n8n.
3. Start API/n8n, check health endpoints, confirm a known onboarding and asset can be read with proper authorization, and run a synthetic connector test using the existing idempotency key.
4. Confirm no duplicated external resource and verify a pending dispatch/recovery record. Record restore duration, data loss window and exact command outputs in the customer runbook.

**Historical snapshot evidence:** on 2026-09-28, before migration `0003` and the tenth workflow import, `pg_dump -Fc` and `pg_restore --no-owner` succeeded for both 13 MB business and 16 MB n8n databases into temporary isolated databases. Original and restored counts matched: business `(workspaces,clients,won_deals,onboardings,plan_revisions)=(2,61,93,93,93)` and n8n `(workflows,webhooks,executions,credentials)=(9,5,15,1)`. The verification databases and temporary dumps were removed afterward. This snapshot does not verify the latest schema/workflow pack. Starting API/n8n against restored data, credential decryption, asset-volume restore and customer recovery-time objectives remain unverified. PostgreSQL migrations ran in the local demo; a production migration and rollback path requires verification before a customer launch.

## Failure handling

Check the business API health and n8n execution log, then locate the onboarding timeline, `workflow_dispatches`, `provisioning_operations`, `task_cards`, `external_resources` and outbox rows by onboarding ID. A known successful resource is reused. For 429/timeouts/5xx, apply bounded retry with jitter and `Retry-After` when available. A timeout after an external write may have succeeded; mark it uncertain and reconcile the provider-side resource before retry. An unknown card result requires a provider lookup and operator-confirmed external ID/status or confirmed absence; DEMO can reconcile against its simulator. A stale card claim is skipped if the desired status/key changed, while an in-flight/unknown write retains its provider key until its outcome is known and can then schedule a newer update. Connected board reconciliation requires a verified To Do list ID as well as the board ID; the operator UI collects both. A delivered n8n trigger older than five minutes can return to `pending` only when business state is incomplete and there are no uncertain/claimed provider operations or queued welcome email. Auth/schema/validation errors are permanent until configuration or data is corrected. Do not delete a successful folder to conceal a board failure. The [n8n error workflow documentation](https://docs.n8n.io/build/flow-logic/handle-errors-gracefully) explains when its Error Trigger fires; confirm behavior using triggered executions, as a manual editor run is insufficient.

## Retention and redaction

Choose a customer-approved retention schedule for proposals, answers, assets, timeline, executions and n8n execution data before connected launch. Default n8n/API logs and tracing must be reviewed for personal data and credentials; redact request bodies, signatures, invite URLs and model source content. Purge demo data only in the demo namespace. An installation needs documented backup retention and verified deletion procedures for customer content. No retention interval is claimed as implemented or tested here.

## Customer onboarding checklist

Agree on service templates and approved scope mapping; create least-privilege Drive/Trello test accounts, an authorized SMTP sender and recipients, and a model budget; configure TLS/domain and credential storage; map workflow credentials and IDs; run five triggered demo scenarios plus a connected smoke test; perform an isolation check and restore smoke test; record who owns support, backup and account access.
