# ADR 0001 — n8n owns business orchestration

**Status:** accepted for the pilot, 2026-09-28.

## Decision

n8n owns event triggers, branching, connector calls, schedules and error routing. The FastAPI business API owns durable state and authorization. A small LangGraph service returns an AI-only typed plan draft. Parent workflows call explicit Drive/Trello sub-workflows.

## Why

The brief requires an executable n8n workflow pack. A second Python orchestrator for the same business journey would make retries and approvals ambiguous. The AI task benefits from a visible fixed graph, but it cannot silently perform external writes.

## Tradeoff

The system runs multiple services and needs reference wiring after import. The gain is one owner per responsibility and a provider-independent business database. Actual workflow execution and reference mapping remain acceptance gates. n8n documents [sub-workflows](https://docs.n8n.io/build/flow-logic/break-workflows-into-smaller-parts) and [error workflows](https://docs.n8n.io/build/flow-logic/handle-errors-gracefully).
