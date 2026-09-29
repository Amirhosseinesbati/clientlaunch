# Synthetic demo dataset card

**Label:** Synthetic demo dataset. Every client, deal, address, brand file, revenue or provider response in this dataset is fictional. No real client outcome is claimed.

## Intended use and provenance

The dataset exercises a local agency onboarding workflow and isolated UI states. Structured scenario definitions and deterministic templates create the ground truth. A model response is never used to label itself. Reserved `example.com` names/addresses and fabricated external identifiers prevent accidental contact with real parties. Local connector rows represent Drive/Trello equivalents, not live accounts.

The full generator is `python -m scripts.seed --mode full` with a fixed seed and configurable reference date. A fast seed is for developer iteration. On 2026-09-28, the implementation team applied Alembic migrations to an isolated local **SQLite** database, then ran fast and full seed commands. The following counts were printed there. A PostgreSQL/Compose run and referential-integrity audit remain pending.

| Entity or scenario | Brief target | Verified full-seed count |
|---|---:|---:|
| Clients | 60 | 60 in local SQLite full seed |
| Won deals | 90 | 90 in local SQLite full seed |
| Service templates | 8 types | 8 service types / 16 workspace-scoped rows in local SQLite full seed |
| Checklist/task rows | 1,000 | 1,000 in local SQLite full seed |
| Synced synthetic board cards | No separate brief target | 649 in local SQLite full seed |
| Assets / realistic small placeholders | 250 | 250 in local SQLite full seed |
| Intake submissions | 180 | 180 in local SQLite full seed |
| Partial-failure histories | 30 | 30 operation histories in local SQLite full seed |
| Evaluation scenarios | 80 | **80 generated and counted locally**: 25 development, 55 held out |

The fast seed printed 8 clients/deals, 79 checklist rows, 5 assets/submissions and 2 partial failures. The evaluation scenario manifest is `evals/datasets/manifest.json`. Its reference date defaults to 2026-09-28 and seed to `8042`. Regenerate with `python evals/generate_scenarios.py --seed 8042 --reference-date 2026-09-28`. The generator itself was run using the bundled Python interpreter on 2026-09-28; it emitted 80 distinct IDs with the declared split. This is a dataset-structure check, not a quality result.

Three additional 80-scenario suites, `evals/datasets/fresh/`, `evals/datasets/fresh2/` and `evals/datasets/fresh3/`, were later generated for DEMO extractor checks. The original and these three suites were inspected for failures and are historical diagnostics. A separate independent Fresh4 suite lives in `fresh4_output/` with 80 cases (25 development, 55 held out), input requests, labels, manifest and results. It met the synthetic DEMO numeric targets before its results were inspected; later extractor changes would require another independent set.

## Entity relationships and distributions

Deals belong to clients within a demo workspace; the seed is intended to include two isolated workspaces. A won deal selects one or more purchased service codes from website, brand, SEO, content, ads, analytics, email and ecommerce. Approved plans use versioned service templates; checklist items, answers, assets, reminder events, provisioning operations and handoff evidence hang from an onboarding. The database enforces key relationships and uniqueness constraints; see [ARCHITECTURE.md](ARCHITECTURE.md).

The evaluation set rotates across service categories and sometimes combines two purchased services. It includes scope-specific requirements, an unpurchased-service mention every fifth case, urgent wording in some cases, due and reminder frequency boundaries, paused/ready/handed-off states, folder-created/board-missing recovery cases, and ambiguous provider outcomes. The held-out set uses distinct fictional entities, later reference dates and different scope phrasing from development. It tests limited wording generalization; it is **not** a real proposal distribution.

## Ground truth and leakage control

Each suite separates `requests.jsonl` (input payloads and split labels) from `ground_truth.jsonl` (expected scope items, required inputs, reminder decisions and recovery actions). This includes `fresh4_output/`. The runner maps labels by scenario ID only **after** the planning service responds. Do not load ground truth into template retrieval, prompts, production fixtures or model context. Do not tune on inspected held-out answers and then reuse the same suite as release evidence.

The scenario generator authors labels from service/template choices and explicit feature flags. Scope precision and required-input recall are measured only against actual `/plan` responses. Reminder and recovery labels are available for later triggered integration scoring; the current planning runner explicitly does not score them.

## Limitations and sensitive-data handling

The phrases are compact English fixtures; they do not represent legal proposal language, multilingual contracts, true attachment diversity, provider API behavior or human stakeholder ambiguity. Seeded performance cannot establish accuracy on a customer’s documents. No hidden real data is bundled. Before a customer pilot, validate real templates with the customer, get permitted test data, inspect a human-reviewed sample, set retention rules, and run connected connector/model tests.
