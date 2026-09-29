# Dependency and license inventory

**Inspected:** 2026-09-28. This is an inventory of pinned source dependencies and observed local builds, not a customer deployment software bill of materials. Record deployed image digests and retest node typeVersions before a customer installation.

## Runtime choices

| Component | Declared or planned version | Observed validation |
|---|---|---|
| n8n Community | Container tag `2.40.7` | [Official release](https://github.com/n8n-io/n8n/releases/tag/n8n%402.40.7) published 2026-09-25; container ran, earlier ten-workflow/94-node pack imported/published, five webhooks registered, and Drive/Trello sub-workflows executed in the Willow provisioning/recovery test. Latest 96-node export passed static validation but was not reimported after Docker overlayfs I/O failure |
| PostgreSQL | Compose image `16.10` | Container ran; both databases passed isolated dump/restore count checks. n8n warned that PostgreSQL 16 gets compatibility support only. |
| Python | Docker base `python:3.12.11-slim` | API and AI images built and ran successfully |
| FastAPI / Pydantic | Locked `0.141.1` / `2.13.5` | API health and signed intake path ran earlier; 17/17 API tests passed locally after connected-startup, viewer redaction, stale-dispatch and card/board-reconciliation changes |
| SQLAlchemy / Alembic / psycopg | Locked `2.1.1` / `1.20.0` / `3.3.6` | Alembic migrated PostgreSQL through `0003`; both database dumps restored into isolated copies before that migration and the tenth workflow import |
| LangChain / LangGraph | Locked `1.4.2` / `1.2.12` | Local DEMO LangGraph pipeline executed in 80 `/plan` calls |
| LangGraph PostgreSQL checkpoint | Locked `3.1.2` | AI service ran in DEMO; checkpointer is configured but restore of its live state remains pending |
| React / TypeScript / Vite | Locked React/React DOM `19.3.0`, TypeScript `5.9.3`, Vite `8.3.1`; TanStack Query `5.104.0`, Tailwind `4.3.3`, Vitest `5.0.2` | Latest production Vite build and TypeScript typecheck passed after connected-board UI change; 3/3 web tests passed; CI execution pending |
| Web build/server images | `node:24.18.0-bookworm-slim`, `nginx:1.31.0-alpine3.23` in Dockerfile | Image built; web container served HTTP 200 |
| Argon2 / httpx / python-multipart | Locked `25.1.0` / `0.28.1` / `0.0.32` | Auth/API route tests passed locally |

Root `uv.lock` records the universal 71-package Python resolution, and root `requirements.lock` exports exact versions with hashes. Both Python Dockerfiles install `requirements.lock`; `apps/api/requirements.in` and `apps/ai/requirements.in` remain human-readable input constraints. `apps/web/pnpm-lock.yaml` pins the JS dependency graph; pnpm `11.19.0` was used for the reported frontend checks. Record actual image digests as well as tags for a customer deployment. The successful earlier local n8n imports, intake and forced-failure folder/board recovery provide DEMO runtime evidence; the latest 96-node workflow changes and scheduled dispatch retry still require triggered tests.

## License review before redistribution

The n8n [source license](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) uses the Sustainable Use License for most source, with separate enterprise-licensed files. It permits internal business use under stated conditions and restricts distribution/availability for commercial purposes. The [n8n license overview](https://github.com/n8n-io/n8n/blob/master/README.md#license) describes the dual licensing model. The proposed offer is customer-specific installation and customization of this **workflow pack and companion service**, with the customer operating its own licensed n8n instance. Do not assume this grants rights to redistribute n8n binaries, embed n8n into a paid product or operate a hosted n8n service. Obtain a license/legal review for a different commercial model.

For every bundled Python/JavaScript dependency, frontend icon/font/image, model and fixture file, produce a release SBOM and verify the actual license and notice obligations before redistribution. No third-party asset right is claimed from an unreviewed package. The project screenshots and synthetic examples are not customer testimonials.

## Upgrade policy

Change exact versions in one controlled PR, rebuild from lockfiles, import the pack into a fresh instance, run actual triggered scenarios, replay duplicate/recovery tests, and inspect portal screenshots before updating a customer. Store an export/backup of n8n workflow settings and encryption key before upgrade. A release note announcing a newer version does not alone validate the pack.
