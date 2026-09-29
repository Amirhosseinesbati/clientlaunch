# ClientLaunch business API

The FastAPI application is `apps.api.main:app`. OpenAPI is available at `/openapi.json` and `/docs` on the API host. JSON routes below use `/api`; local connector simulators use `/sim`. n8n owns workflow coordination and calls state commands with `X-Internal-Key`. The browser calls only operator and client routes.

## Authentication and configuration

- Operator login: `POST /api/auth/login` with `{ "email": "operator@northstar.example.com", "password": "<DEMO_ADMIN_PASSWORD>" }`. The response sets an HttpOnly `clientlaunch_session` cookie (`SameSite=Lax`; `Secure` when `COOKIE_SECURE=true`) and returns `{user,csrf_token,expires_at}`. Include `credentials: "include"` and `X-CSRF-Token` on mutating requests. `GET /api/auth/me` returns `{user,csrf_token}` after a refresh; `POST /api/auth/logout` revokes the session. No operator bearer token is exposed to browser JavaScript.
- Roles: `admin`, `operator`, `viewer`. The first two can approve and operate; viewers only read. All operator reads/writes are scoped to the user's workspace. Viewer detail omits `onboarding.portal_link` and sets the welcome message body to `null`, since both can contain a client access token. Seeded demo workspaces are `northstar` and `cedar`.
- n8n/internal commands require `X-Internal-Key: <INTERNAL_KEY>`. The browser must never receive this key. `GET /api/onboardings/{id}` accepts either an operator session or the internal key.
- A won-deal event must carry `X-ClientLaunch-Signature: sha256=<hex>`, computed as HMAC-SHA256 with `WEBHOOK_SECRET` over `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`. Signed payload fields: `workspace_slug,event_id,external_deal_id,client:{name,email},services,approved_scope,proposal_text,timeline,account_owner_email`.
- `APP_MODE=DEMO|CONNECTED` labels the environment. `CONNECTOR_MODE=demo|connected` selects simulator versus live connector path. Simulators reject requests in connected mode. Connected API startup requires `APP_MODE=CONNECTED`, `MODEL_MODE=connected`, distinct non-demo `INTERNAL_KEY` and `WEBHOOK_SECRET` values of at least 32 characters, and `COOKIE_SECURE=true`. `SMTP_FROM` is required for connected welcome/reminder dispatch. Missing credentials never turn into demo success.

## Operator and workflow routes

| Method | Route | Caller | Purpose |
| --- | --- | --- | --- |
| GET | `/api/health` | public | Database-backed `{status:"ok",mode,connector_mode}` or 503. |
| POST | `/api/events/won-deal` | signed source/n8n | Persist a versioned deal/onboarding. Response `{onboarding_id,status,duplicate,event_id}`. Duplicate event ID with changed bytes or deal scope returns 409. |
| GET | `/api/templates` | operator/internal | Active template versions with `service_code`, description, checklist, folder and board blueprints. |
| GET | `/api/onboardings` | operator | `{items:[...]}` workspace-scoped overview. |
| GET | `/api/onboardings/{id}` | operator/internal | Full scoped state snapshot, including recorded handoff summary and source IDs after closure. Client portal responses omit this operator record. |
| POST | `/api/onboardings/{id}/plan` | internal | Save AI plan draft and create a hash-bound, expiring approval. |
| POST | `/api/onboardings/{id}/approval` | operator | Single-use plan approval/rejection. Approved plans enqueue a durable n8n dispatch. |
| POST | `/api/onboardings/{id}/provisioning/claim` | internal | Concurrent-safe operation claim and idempotency key. |
| GET | `/api/onboardings/{id}/provisioning/folders/next` | internal | Return the next child folder whose parent is confirmed, or a done/blocked state. |
| POST | `/api/onboardings/{id}/provisioning/{operation_id}/complete` | internal | Record success, failure, or unknown provider outcome and external ID immediately. |
| GET | `/api/onboardings/{id}/task-sync/pending` | internal | Pending board card creates/updates, as a top-level array. |
| POST | `/api/onboardings/{id}/task-sync/{operation_id}/claim` | internal | Lease a card operation before external write. Body includes `expected_status` and `expected_idempotency_key`; a stale snapshot returns `execute:false,status:"stale"`. Expired lease becomes uncertain. |
| POST | `/api/onboardings/{id}/task-sync/reconcile` | internal or operator | In DEMO, internal `{}` reconciles expired card claims against simulator state. An operator must provide `operation_id` and a confirmed external card/status or confirmed absence. Connected mode does not guess a provider outcome. |
| POST | `/api/onboardings/{id}/task-sync/{operation_id}/complete` | internal | Record card external ID and synced checklist state. |
| POST | `/api/client-submissions/{submission_id}/process` | internal | Idempotently map stored intake answers to pending board card updates. |
| POST | `/api/onboardings/{id}/recover` | operator | Retry known failure, reconcile uncertain outcome, or request manual compensation. |
| POST | `/api/onboardings/{id}/welcome` | internal | Prepare approved welcome. Demo stores simulated outbox delivery; connected returns SMTP payload requiring later ack. |
| POST | `/api/outbox/{id}/ack` | internal | Record connected SMTP provider message ID after real delivery. |
| PATCH | `/api/onboardings/{id}/checklist/{item_id}` | operator | Edit due date and owner without changing original contract. |
| POST | `/api/onboardings/{id}/state` | operator | `{action:"pause"|"resume",reason?}`. |
| POST | `/api/onboardings/{id}/handoff` | operator | Close only a ready onboarding with factual summary/evidence links. |
| POST | `/api/reminders/evaluate` | internal | Draft due reminders from current state, maximum three sends per item and minimum three days apart. |
| POST | `/api/onboardings/{id}/reminder-decisions` | internal | Scoped reminder evaluation. |
| POST | `/api/reminders/{id}/approval` | operator | Approve/reject drafted reminder. |
| GET | `/api/reminders/approved-pending` | internal | Top-level array of actionable approved reminder messages for n8n. |
| POST | `/api/reminders/{id}/dispatch` | internal | Record demo delivery, or record connected provider message ID after n8n SMTP send. |
| GET | `/api/workflow-dispatches/pending` | internal | First reassess accepted triggers delivered at least five minutes ago against business state. Complete ones are marked `completed`; safely replayable incomplete ones return to `pending`. Return up to 20 pending approval, submission and recovery triggers, ordered by fewest recorded attempts then creation time. |
| POST | `/api/workflow-dispatches/{id}/attempt` | internal | Atomically record a sweep attempt and return `execute:false` if the row was already delivered. |
| POST | `/api/workflow-dispatches/{id}/ack` | internal | Acknowledge accepted n8n trigger. |
| POST | `/api/workflow-errors` | internal | Persist shared n8n Error Trigger exception. |
| GET | `/api/workflow-errors/unattributed` | internal | Inspect n8n errors lacking onboarding context without exposing them across workspaces. |
| GET | `/api/exceptions` | operator | Visible business exception queue. |

The latest workflow export also defines authenticated n8n `POST /webhook/clientlaunch/reminder-run` with `{}` for a controlled DEMO reminder run, alongside the daily schedule. It is in the 96-node source pack and has **not** been imported or triggered in the local n8n instance.

Plan body:

```json
{
  "checklist": [{"key":"brand_logo","title":"Upload logo","required":true,"source":"template","service_code":"website","client_visible":true}],
  "deliverables": ["Website launch"],
  "risks": [],
  "missing_inputs": ["Logo"],
  "welcome_draft": "Hello, welcome to your project.",
  "summary": "Website onboarding",
  "suggestions": []
}
```

`source:"scope"` requires an `evidence` literal substring of the approved scope. Every checklist `service_code` must be purchased. Missing deterministic template tasks are inserted by the API. Unsupported ideas stay in `suggestions`; they never become contractual checklist items automatically.

`GET /api/onboardings/{id}` returns:

```json
{
  "onboarding": {"id":"...","status":"awaiting_approval","substate":null,"client_name":"...","client_email":"...","workspace_name":"...","owner_name":"...","service_names":["website"],"progress_percent":0,"required_complete":0,"required_total":0,"connector_mode":"demo","project_name":"...","folder_name":"...","board_name":"...","reference_date":"2026-09-28","portal_link":"..."},
  "deal": {"external_deal_id":"...","approved_scope":"...","proposal_text":"...","services":["website"],"timeline":{}},
  "plan": {"id":"...","revision":1,"proposal_hash":"sha256 hex","status":"pending","checklist":[],"summary":"...","deliverables":[],"risks":[],"missing_inputs":[],"welcome_draft":"...","suggestions":[]},
  "checklist": [], "operations": [], "resources": [], "folder_structure": {"root":{"name":"...","external_id":null,"url":null,"status":"planned"},"folders":[{"id":null,"service_code":"website","folder_key":"service","name":"Website","parent_folder_key":"root","external_id":null,"status":"planned"}],"planned_count":1,"complete_count":0,"complete":false}, "approvals": [], "events": [], "assets": [], "submissions": [], "welcome": [], "reminders": [], "task_cards": [], "handoff": null
}
```

Approval body: `{ "plan_revision_id":"...", "proposal_hash":"...", "decision":"approve" }`. The approval is single-use and expires after two days. The response includes `dispatch_status`. API commits a `workflow_dispatches` row before best-effort POST to `N8N_PROVISION_WEBHOOK_URL`; n8n can poll pending rows after a crash. Client intake uses the same mechanism with `N8N_SUBMISSION_WEBHOOK_URL`.

Provisioning claim body: `{ "system":"drive", "action":"create_folder", "request_payload":{"name":"..."} }` or `system:"trello",action:"create_board"`. New claim response:

```json
{"execute":true,"onboarding_id":"...","operation_id":"...","idempotency_key":"clientlaunch:<onboarding-id>:drive:create_folder","status":"claimed","external_resource":null,"request_payload":{"name":"..."},"connector_mode":"demo"}
```

Known resource returns `execute:false`, `status:"succeeded"`, and `external_resource:{external_id,url,name}`. A pending or unknown operation also returns `execute:false`; n8n must route it to reconciliation. Completion body: `{ "external_id":"...", "url":"...", "name":"..." }` (success by default), or `{ "outcome":"failed"|"unknown", "error":"..." }`. Trello board completion also needs `todo_list_id` in connected mode; the demo simulator supplies it. Operator `recover` accepts `{operation_id,decision:"retry"|"reconcile"|"compensate",external_id?,confirmed_absent?,todo_list_id?}`. A connected board reconciliation that confirms an external board also requires the verified `todo_list_id` so later card writes target the right list; the operator UI collects it. Internal recovery accepts `{}` and returns `{onboarding_id,can_retry,status,substate,results}` after safe ledger evaluation. An uncertain connected operation cannot be retried until a provider lookup confirms an external ID or absence. Compensation is only recorded for operator action; no resource is deleted automatically.

The approved plan freezes each purchased template's folder blueprint. After the root Drive folder is confirmed, n8n repeatedly calls `GET .../provisioning/folders/next`. It returns `{done,blocked,remaining_count,folder}`; a runnable `folder` contains `id`, `service_code`, `folder_key`, `name`, and `parent_external_id`. For each folder, claim `{system:"drive",action:"create_child_folder",folder_id:"..."}`. The server supplies `request_payload:{name,parent_id,onboarding_id,folder_id}` and a unique idempotency key. Record each provider result through `.../complete`, then query the next folder. A blocked or uncertain folder stops the loop for recovery. The onboarding enters `waiting_for_client` only after the root, all planned child folders, and the task board are confirmed.

After board completion, `GET /api/onboardings/{id}/task-sync/pending` returns a top-level array. Each operation contains `operation_id`, `action` (`create` or `update`), `external_board_id`, `todo_list_id`, `title`, `description`, `due_date`, `status` (`open`, `completed`, or `needs_review`), `idempotency_key`, `connector_mode`, `checklist_item_id`, and optional `external_card_id`. Before a board exists it returns `[]`. n8n calls `.../claim` with `{expected_status:<pending status>,expected_idempotency_key:<pending key>}`, branches on `execute`, writes to the demo simulator or Trello, then calls `.../complete` with `{external_id,status}`. Concurrent client edits preserve an already claimed or unknown provider write and its key. After that observed outcome is recorded, a differing desired status schedules one later update. The board preview uses only cards actually acknowledged. `POST /api/client-submissions/{id}/process` returns `{submission_id,onboarding_id,processed,duplicate,pending_operations}`; it is idempotent and updates desired board statuses. Readiness waits for required client items and acknowledged board card updates.

`POST /api/onboardings/{id}/task-sync/reconcile` allows an authenticated operator to resolve an expired or unknown card claim with `{operation_id,external_id,status}` or `{operation_id,confirmed_absent:true}`. A matching DEMO simulator card is verified before recording its ID/status. In connected mode, the operator must verify the real provider outcome; automatic replay of an uncertain write is blocked. The internal empty-body mode checks DEMO simulator cards and is called by the latest task-sync workflow, which has only static validation until its 96-node pack is imported.

The pending-dispatch sweep treats a webhook 2xx as acceptance, then checks business progress after five minutes. A delivered approval/recovery is complete only when provisioning, cards and welcome are settled; a submission also needs its processing record and synced cards. Incomplete work is requeued only when provisioning/card operations have no claimed, unknown or failed state and no queued welcome SMTP item can have an uncertain send. This stale-delivery check has isolated API test evidence, not a triggered n8n run.

`POST /api/onboardings/{id}/handoff` requires a ready onboarding and an operator-written summary. The persisted `handoff` detail contains `{id,summary,evidence,created_at}`, where evidence links recorded submission, asset and external resource IDs. The operator UI displays that saved summary and links to the associated answers, files and resources after handoff. The latest UI has typecheck evidence; a full runtime handoff remains pending.

Welcome body may be `{}`; the API derives the approved draft, scoped recipient, and subject. Explicit `{recipient,subject,body}` is also accepted, but body must exactly match the approved `welcome_draft`. The API appends the scoped portal link, checklist, owner, and kickoff availability request. Response: `{id,status,dispatch_required,to,from,subject,body,message_key}`. In connected mode, n8n sends only when `dispatch_required=true`, then calls outbox ack with `{provider_message_id}`.

## Client portal

`POST /api/client/exchange` with `{portal_token}` returns a four-hour client bearer token. Invite tokens are onboarding-scoped and expire after 14 days. `GET /api/client/onboarding` returns only client-visible checklist, assets, submissions, progress, and next actions. Client routes require `Authorization: Bearer <client token>`:

- `POST /api/client/submissions`: `{ "answers":[{"checklist_item_id":"...","value":"..."}] }`. A changed answer is marked for operator review and never silently changes the contract.
- `POST /api/client/assets`: multipart `file` and `checklist_item_id`; PNG, JPEG, or PDF only, maximum 5 MB, signature checked. Executable and SVG uploads are rejected. A successful asset creates a scoped intake event for n8n task sync.
- `GET /api/assets/{asset_id}`: workspace/onboarding-scoped download for operator or the matching client.

## Demo connector simulators

All routes require `X-Internal-Key` and `CONNECTOR_MODE=demo`:

- `POST /sim/drive/folders` and `POST /sim/trello/boards` accept `{name,idempotency_key}` (optional `onboarding_id`, `parent_id`, `simulate_failure`, `simulate_timeout`). Key must be server-issued from a claim. Return `{external_id,url,name,duplicate}`; boards also return `todo_list_id`. `simulate_timeout` persists the resource, then returns 504 to test reconciliation.
- `POST /sim/faults/next` accepts `{onboarding_id,system:"drive"|"trello",kind:"failure"|"timeout"}`. The next new simulator write for that onboarding/system consumes the fault. `failure` marks the claimed ledger operation `failed` and returns 503 before creation. `timeout` persists the resource, marks its outcome `unknown`, then returns 504. The recovery workflow can safely retry a known failure or reconcile an uncertain simulator outcome.
- `POST /sim/trello/cards` accepts `{board_id,name,description,due_date?,idempotency_key}` and returns `{id,url,name,status,duplicate}`. `PATCH /sim/trello/cards/{id}` accepts `{status,idempotency_key}` and returns the same shape. A task-sync claim must exist.
- `GET /sim/{system}/resources/by-key/{idempotency_key}` returns `{found:false}` or `{found:true,external_id,url,name}`.
- `POST /sim/smtp/send` accepts scoped recipient, subject, body, and `Idempotency-Key`; writes a demo outbox record only.

All responses and IDs represent persisted business state. Synthetic data and simulated connector responses are explicitly labeled in the UI and handover.
