# ClientLaunch: reuse and client customization

This pass adds real workspace branding and versioned service templates, clearer client requests, invitation status, scoped progress, retained answer drafts, readable scope and receipts. The October 7 design adds a compact operations workbench, responsive detail dialogs and persisted Light/Dark/System appearance. See [DESIGN_AND_THEMES.md](DESIGN_AND_THEMES.md) for design, evidence and appearance behavior.

## Preview without Docker

From `clientlaunch` with the existing frontend dependencies:

```powershell
node scripts/preview_fixture.mjs
```

Open <http://127.0.0.1:4318>. The fixture API binds to loopback port **8318**. Both ports are strict; an occupied port is an error. Stop the command with Ctrl+C.

- Operator: `fixture@clientlaunch.example.com` / `preview`.
- Viewer: `viewer@clientlaunch.example.com` / `preview`.
- Client: `/client`, private code `fixture-willow`, or paste `http://127.0.0.1:4318/client?token=fixture-willow`.
- Atlas Fieldwork is the partial-failure case. Its folder exists in fixture metadata, and its board operation failed. A retry queues a pending fixture operation; no n8n worker completes it.

The fixture keeps fictional changes **in memory** and resets on restart. It creates no database, sends no mail, calls no live provider and runs no n8n/AI service. File uploads record fictional metadata and discard content. Answers complete immediately in this fixture; the real API queues workflow processing. Plan approval and other unsupported orchestration operations return an explicit fixture limitation. This is interaction evidence, not proof of live workflow acceptance.

The frontend can also use the real native API, with its own isolated database, by setting `VITE_API_PROXY_TARGET=http://127.0.0.1:8318` and running Vite on `--host 127.0.0.1 --port 4318 --strictPort`. Do not reuse a live database or `.env` for fixture QA. The fixture already occupies 8318 while running.

## Configure a client's agency workspace

1. Sign in as an operator or admin, then open **Templates & brand → Portal brand**.
2. Set agency name, accent, welcome heading, message and optional support email. The preview reflects unsaved edits; **Save brand** persists settings to the real workspace database.
3. The next scoped client-portal request loads that workspace's saved branding. The accent changes primary client actions and the preview, with readable text contrast. Informational text and progress use theme tokens. Operator authentication and navigation keep the product identity.
4. Brand edits do not change email templates, provider credentials, domains, logo files or already sent messages. Those remain separate deployment/customization work.

Brand fields are validated and capped. Support email must be valid, and accent is a six-digit hex color. Operators/admins can write; viewers can read. Cookie writes require CSRF. A stale version receives 409 rather than overwriting another operator's edits. The real API persists across restarts; the fixture does not.

## Reuse a service template

Open **Service templates**, choose an installed service, and edit its name, description, requests and folder list. Each request has a stable key, title, optional client instructions and a required flag. Add requests when needed; use specific instructions and a secure channel for access rather than asking for passwords. Folder names must be unique, use no slash and fit within 240 characters.

**Save new version** creates an immutable historical version and activates the new version for future plan drafting. Old template rows remain available to approved plan and folder snapshots; existing checklist items, projects and folders are not rewritten. A stale version receives 409. Board columns are preserved by the API and are not edited here. This pass edits existing services; provisioning a new service code still uses the established seed/deployment process.

Review the exact draft plan after a template change. Human approval and provisioning requirements remain in effect. The editor does not bypass won-deal intake, plan review or workflow recovery.

## Client experience and recovery

- Invitation details separate access validity from welcome delivery. `simulated_sent` is labeled **Simulated only · no email sent**. Copying a link sends nothing; viewers cannot access private invite links.
- Client progress counts required **client-visible** requests. Internal checklist items and internal submission answers are excluded from the client payload.
- A single next action opens the corresponding answer field. Completed inputs remain visible; progress is explicitly separate from delivery readiness.
- Drafts are stored per project and request in `sessionStorage`, retain their own text when switching requests, survive a reload in the same tab and clear each request's draft after successful sending. Explicit client signout clears the project's drafts. Storage failure does not prevent memory-only access. Do not treat browser storage as a shared or durable document store.
- A failed response retains edits. If the connection ends before a mutation result is known, refresh and inspect **Answers saved to this project** before resending. The receipt records an accepted submission; checklist progress can update later through n8n. Do not assume a network failure means the server received nothing.
- PNG, JPG and PDF uploads are validated before sending; maximum 5 MiB. Files are sent only by the upload action. The real API still performs its own validation and scoped authorization.
- The public `intake_open` flag disables forms during paused, failed or uncertain states. The API independently enforces lifecycle rules.
- Detail overlays support Escape and focus containment. Detail tabs support arrow keys/Home/End. Pages have skip links and explicit field labels; long content wraps and scrolls naturally.

## Real backend upgrade

New routes: `GET/PATCH /api/workspace/brand`, `GET /api/templates`, and `PATCH /api/templates/{service_code}`. The write bodies include `expected_version`. No credentials are exposed by these routes.

Apply additive Alembic migration **0004_workspace_brand** to an appropriately backed-up, authorized deployment database:

```powershell
.venv\Scripts\python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

Do this in the configured target environment. This pass tested migration upgrade/downgrade/re-upgrade against a new isolated SQLite database, not the user's existing databases or PostgreSQL deployment. For a database already stamped at0003, the migration only adds `workspace_brands`. Downgrading0004 removes its branding table and saved brand data. Template history is stored in the pre-existing table.

Existing n8n workflows and connected adapters have not been imported, published, deployed or exercised live. Docker is unavailable in this environment. AI service8418 and n8n5688 were not started. Real provisioning, uncertain-provider reconciliation, reminder delivery and SMTP still need the existing runtime acceptance process with authorized providers.

## Verification and artifacts

From the project root, using installed dependencies:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests/api -p "test_*.py"
.venv\Scripts\python.exe -m unittest discover -s tests/customization -p "test_*.py"
node scripts/qa_themes.mjs
node scripts/qa_upgrade.mjs
```

In `apps/web`:

```powershell
node_modules\.bin\tsc.CMD -b --pretty false
node_modules\.bin\vitest.CMD run --maxWorkers=1 --no-file-parallelism
node_modules\.bin\vite.CMD build --outDir ../../.runtime/theme-dist --emptyOutDir
```

The isolated browser script runs only when `/api/health` confirms the local fixture. It launches its own headless Chrome profile, blocks remote Google font requests and never touches the shared browser. Current screenshots and machine-readable results are under [`screenshots/theme-2026-10-07`](../screenshots/theme-2026-10-07/). The October 6 evidence is retained. Start the preview before browser QA. QA resets and mutates fictional fixture data.

No lint script/config exists in this frontend. TypeScript includes strict typing and unused-code checks. API tests verify workspace isolation, role/CSRF boundaries, validation, optimistic version conflicts, immutable template history, client progress and answer redaction. Browser checks verify actual form actions, failures/retries, repeated saves, draft reload/signout, branding consumption, mobile overflow, dialog semantics and Escape.
