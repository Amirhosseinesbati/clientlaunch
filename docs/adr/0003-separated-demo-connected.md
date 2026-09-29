# ADR 0003 — Keep DEMO and CONNECTED explicit

**Status:** accepted for the pilot, 2026-09-28.

## Decision

The demo uses a deterministic scope extractor, local Drive/Trello simulators, generated fictional records and an outbox. Connected mode requires configured provider/model credentials and authorized destinations. An unavailable connected provider fails or becomes uncertain; it never becomes a synthetic success.

## Why

A rich local walkthrough must be safe and reproducible without buying services or contacting real clients. Equivalent adapter contracts allow later provider-specific validation without changing the business workflow shape.

## Tradeoff

Fixture correctness does not establish model accuracy, provider compatibility or delivery reliability. The portfolio and handover must label synthetic effects and leave live verification pending until measured.
