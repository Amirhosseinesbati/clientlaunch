# ADR 0002 — Claim connector writes in a durable ledger

**Status:** accepted for the pilot, 2026-09-28.

## Decision

Create or reuse a unique `provisioning_operations` row before a folder or board write. Persist the external ID in `external_resources` immediately after a known success. Reuse the same idempotency key and return known resources on retry. An ambiguous timeout enters reconciliation; no automatic destructive compensation occurs.

## Why

n8n execution retries can repeat a side effect. A database uniqueness constraint makes one business operation claim visible across workers and restarts. A successful folder must remain visible if board creation fails.

## Tradeoff

The ledger adds state transitions and operator work for uncertain provider responses. It cannot guarantee exactly-once delivery across arbitrary third-party APIs; live connector contract tests and triggered retry/restart tests are still required.
