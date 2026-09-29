# ClientLaunch — independent portfolio case study

**Portfolio label:** Independent portfolio project with a synthetic agency and local service simulators. No customer, testimonial, live revenue, production deployment or measured efficiency improvement is claimed.

## Case study

**Problem.** Small agencies can lose context between a signed proposal and delivery kickoff. Folder creation, task setup, welcome messages and missing-input follow-up often happen in separate tools, making duplicate work and silent scope changes plausible.

**Product.** ClientLaunch turns a signed won-deal event into a versioned onboarding plan. A human reviews the exact plan hash before n8n coordinates a root project folder, frozen service-specific child-folder trees and a board with cards. The client portal collects answers and bounded assets; the operator console shows checklist status, the planned/created folder hierarchy, timeline and recovery ledger. A fixed LangGraph pipeline adds evidence-backed client-specific inputs to deterministic service templates. Demo mode keeps every external effect in local simulators/outbox.

**Engineering approach.** Business state, access control, approval and idempotency live in a FastAPI/PostgreSQL service; n8n owns workflow branching, schedules and connector calls; the AI service returns only a typed draft. A five-minute sweep retries pending approval, submission and recovery dispatches with a 20-item cap and an attempt-count ordering. The latest API also checks accepted triggers after five minutes against business state and requeues only safe incomplete work, while unknown card writes require reconciliation. This allows a partial failure after Drive-equivalent folder creation to retain the folder ID while board work resumes or is reconciled. See [ARCHITECTURE.md](ARCHITECTURE.md) and [EVALUATION.md](EVALUATION.md) for code structure and actual evidence.

**Current result.** The source includes the stated components and reproducible evaluation scenario generation. In-process calls to the actual DEMO `/plan` route completed five 80-scenario synthetic suites. On the independent 55-case Fresh4 held-out suite, scope precision was **35/35 (100%)** and required-input recall was **245/258 (95.0%)**, meeting both synthetic DEMO numerical targets. A same-set regression after a template-key contract fix retained those scores; it is not a new independent evaluation. Personalized scope recall was 35/48 (72.9%), so human review remains important. These are deterministic fixture results, not connected-model accuracy. The Docker demo imported and published a ten-workflow/94-node pack; signed intake, duplicate/conflict handling and invalid-signature rejection ran through n8n. The user-authorized synthetic Willow Harbor Studio plan was approved once. A forced board failure occurred after root and seven child folders; operator recovery reused them and created one board, six cards and a welcome outbox item. The onboarding reached `waiting_for_client`. A scoped client submission completed five of six checklist items and matching board cards; the logo asset remains open. The latest 96-node source adds an authenticated reminder webhook and card reconciliation, and the API/UI now include safe stale-dispatch retry and persisted handoff detail. Those additions passed local tests/static validation but have not run through the newer n8n pack because Docker overlayfs returned an I/O error. Earlier database-only dump/restore checks passed. Browser captures of preapproval, failure and recovery were saved. Client completion, scheduled retries/reminders, connected-provider behavior and customer outcomes remain unverified. No impact number is presented.

## 60–90 second demo script

1. Show the synthetic agency console and explain the fictional data label. Submit a signed website deal fixture.
2. Open the resulting plan: point to purchased-service template tasks, evidence-backed additions and the proposal revision/hash. Approve it.
3. Follow the triggered n8n execution to the local Drive/Trello equivalents and demo welcome outbox; show the persisted external IDs in the operator ledger.
4. Open the scoped client portal, upload a small sample brand asset and complete one answer. Show progress tied to required rows.
5. Trigger a board failure after folder creation, then recover. Compare resource IDs before and after to show reuse. Close with the factual handoff summary when ready.

The signed intake, exact approval, forced board failure/recovery and five client answers have local triggered n8n evidence. The logo upload, reminder and handoff sequence remains a presenter script until observed end to end.

## 3–5 minute technical walkthrough

Explain the HMAC event contract and two-layer deduplication; open the six-node AI graph and its typed response; show the plan revision/hash approval check; trace n8n parent/sub-workflow IDs from `manifest.json`; inspect an operation claim, external ID, uncertain state and reconciliation path; show a client session restricted to one onboarding and a blocked cross-workspace request; finish with the synthetic held-out evaluation protocol and operational limits.

## Three content angles

1. How an approval hash prevents an edited onboarding plan from silently authorizing external writes.
2. A durable provisioning ledger for third-party timeouts and partial success.
3. Splitting n8n business orchestration from a small, typed LangGraph planning task.

## Verified visuals

The local DEMO capture script saved exact-onboarding operator states at 1440, 1024 and 390 pixels. A curated set from 2026-09-28:

| View | Saved capture |
| --- | --- |
| Overview before approval, desktop | [preapproval-overview-1440.png](../screenshots/preapproval-overview-1440.png) |
| Plan review before approval, mobile | [preapproval-detail-390.png](../screenshots/preapproval-detail-390.png) |
| Failed resource ledger, desktop | [failure-detail-1440.png](../screenshots/failure-detail-1440.png) |
| Failed resource ledger, mobile | [failure-detail-390.png](../screenshots/failure-detail-390.png) |
| Recovered resources, desktop | [recovered-detail-1440.png](../screenshots/recovered-detail-1440.png) |
| Recovered resources, tablet | [recovered-detail-1024.png](../screenshots/recovered-detail-1024.png) |
| Recovered client portal, mobile | [recovered-client-390.png](../screenshots/recovered-client-390.png) |

These show local synthetic states, not customer data. The client-intake and final handoff screens still need captures after those flows run; keyboard/focus and contrast review is also pending.

## Resume bullet templates

- Built an independent ClientLaunch pilot combining n8n workflows, a FastAPI business API and a typed LangGraph planning service for agency onboarding; local approval/provisioning/recovery verified, broader runtime acceptance pending.
- Designed version-bound approval and idempotent provisioning records for simulated Drive/Trello workflows; a triggered board failure after folder creation recovered without repeating successful folder operations.
- Built reproducible synthetic evaluation suites with separate answer keys; the independent Fresh4 DEMO fixture run measured 100% scope precision and 95.0% required-input recall on 55 held-out cases, meeting the synthetic numerical targets.
