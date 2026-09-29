# Deterministic demo fixture evaluation

Run date (UTC): 2026-09-28T01:04:13+00:00.

The actual FastAPI `/plan` route and LangGraph demo extractor were called in process. These synthetic fixture scores do not establish connected-model quality, n8n execution, provider behavior or customer accuracy.

| Split | Completed calls | Scope precision | Scope recall diagnostic | Required-input recall | Result file |
|---|---:|---:|---:|---:|---|
| development | 25/25 | 22/22 (100.0%) | 22/22 (100.0%) | 122/122 (100.0%) | `fresh2_planning_development_demo.json` |
| held_out | 55/55 | 22/23 (95.7%) | 22/48 (45.8%) | 232/258 (89.9%) | `fresh2_planning_held_out_demo.json` |

The held-out DEMO required-input recall is below the 90% release target. The inspected held-out set must not be reused as unbiased post-fix evidence. Runtime n8n journeys, browser screenshots and connected-model tests remain pending.
