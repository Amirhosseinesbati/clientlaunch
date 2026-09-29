# ClientLaunch — product specification and delivery scope

**Status:** independent portfolio pilot in progress. This document describes the intended v1 behavior and the source layout as inspected on 2026-09-28. It does not certify a production deployment.

## Buyer and outcome

ClientLaunch is a customer-specific onboarding installation for a small agency. A signed won-deal handoff becomes a reviewable plan, project folders and a task board, a welcome message, a client checklist, and an evidence-linked delivery handoff. The customer buys implementation and configuration for its own operation, subject to the n8n license assessment in [COMMERCIALIZATION.md](COMMERCIALIZATION.md).

## People and access

| Actor | Primary tasks | Access boundary |
|---|---|---|
| Agency admin | Configure an installation and administer operators | One workspace in the pilot |
| Account owner/operator | Review plan, approve exact revision, recover provisioning, set due dates, hand off | Workspace-scoped records |
| Viewer | Read agency onboarding state | No business mutations |
| Client | Answer intake, provide approved file types, see next actions | One onboarding through an expiring invite/session |
| n8n service | Trigger and coordinate business workflow | Server-to-server key only |

The default sale is **one agency per installation**. Two synthetic workspaces are a test fixture for isolation, not a promise of self-service SaaS tenancy.

## Main journey

1. A QuoteFlow-compatible JSON event arrives at the signed webhook. The business API checks its HMAC, schema, workspace, account owner, service codes, event ID, and deal identity. Replays with the same payload return the same onboarding; conflicting reuse returns an error.
2. n8n asks the AI service to parse the approved scope, retrieve purchased-service templates, propose additional evidenced inputs, identify gaps and risks, draft a welcome note, and validate service scope. The business API stores a versioned plan and exact proposal hash.
3. An authenticated operator approves that revision. Approval is single use and expires. n8n then coordinates folder and board sub-workflows. A durable operation row and provider idempotency key track each write. An unknown outcome requires reconciliation before retry.
4. The approved welcome message goes to the **synthetic demo outbox** or configured authorized SMTP. The client exchanges a scoped invite for a session, sees the checklist, answers questions, and uploads bounded PNG/JPEG/PDF assets.
5. Scheduled reminder evaluation proposes capped reminders only for eligible outstanding items. Internal review decides dispatch. Paused or completed onboarding must be excluded.
6. The application calculates readiness from required checklist completion and recorded external resources. An operator closes with a factual handoff summary that links submission, asset, and resource IDs.

## Explicit modes

- **DEMO:** fictional data, deterministic scope extractor, local Drive/Trello resource simulators and mail outbox. Every visible synthetic or simulated result must be labeled. No outside messages.
- **CONNECTED:** configured model, Google Drive, Trello and authorized SMTP adapters. Missing credentials or provider failure is an error, never a fake success. This path requires account-specific setup and live smoke tests before a customer pilot.

## In-scope v1 behavior

Versioned approved scope, deterministic templates for eight services, editable due dates/owners with timeline records, reviewed scope additions, a customer portal, partial failure recovery, stale/duplicate rejection, client isolation, and a truthful operational timeline. The importable n8n pack is in `workflows/`; the business API is in `apps/api/`, the AI-only service in `apps/ai/`, and the portal in `apps/web/`.

The brief requires a full synthetic set of 60 clients, 90 won deals, 8 templates, 1,000 checklist/task rows, 250 assets, 180 submissions, 30 partial-failure histories, and 80 evaluation scenarios. See [DATA_CARD.md](DATA_CARD.md) for generation and actual count verification.

## Acceptance gates

The release is complete only when a fresh n8n import and at least five **triggered** end-to-end scenarios have been recorded, including duplicate, timeout/reconciliation, a partial folder/board failure, restart, reminders, stale portal link, and cross-workspace rejection. The model targets are precision ≥95% for extracted scope-derived checklist items and recall ≥90% for required labeled inputs on a held-out set. These are targets; actual results belong in [EVALUATION.md](EVALUATION.md).

## Deliberate limits

No billing, public self-service tenancy, enterprise n8n features, automatic deletion of successful third-party resources, or guarantee of exactly-once delivery across external APIs. Kickoff availability is requested through intake; calendar booking is outside this v1. Real customer data, messages, or third-party accounts are not part of the local demonstration.
