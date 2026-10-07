# ClientLaunch workbench and appearance

The October 7 pass replaces the large promotional workspace hero with a compact operations workbench. At desktop widths the client queue and current project sit together. Each row exposes the next action, owner, status and required-input progress. The detail panel keeps approved scope, stage, client requests, resource outcomes, invitation validity, activity and handoff within one readable sequence. At widths up to 1150 px, details open as a focus-contained dialog. Navigation becomes a drawer below 850 px.

## Appearance and branding

**Light**, **Dark** and **System** are available in operator, authentication and client headers, and inside the mobile detail dialog. Fresh visits use Dark. A valid prior choice is preserved; the legacy `clientlaunch_theme` preference is also read. The current key is `clientlaunch.theme`. Only System subscribes to OS appearance changes. If browser storage is unavailable, the choice works for the current page in memory and reload falls back to Dark.

`apps/web/public/theme-init.js` is a blocking, same-origin external head script. It applies the preference before the page body is parsed, sets native `color-scheme` through the token stylesheet, and updates browser chrome metadata. It needs no inline script, eval, provider request or font download. React's `ThemeControl` subscribes to that small runtime; it does not change application keys, remount providers or invalidate data queries. Theme changes preserve the active project, filters, route, drafts, failure messages, selected tab and open dialogs.

`apps/web/public/theme.css` defines explicit surface, foreground, border, status, focus and scrim tokens for both modes. `apps/web/src/styles.css` uses those tokens throughout. The previous `upgrade.css` is retained as historical source but is no longer imported. Text uses local system fonts. Focus indicators, native controls, reduced-motion preferences and narrow screens are supported. Status includes text and symbols as well as color.

The saved agency accent remains project scoped on primary client actions and live preview. Text on that accent uses the existing luminance-based contrast selection. Informational foregrounds and progress use readable theme tokens. Theme selection is a user's display preference; it does not overwrite workspace brand settings or create a new service-template version.

## Reusing this project

Use **Templates & brand** to configure the agency name, welcome copy, accent and support address, then edit an installed service's instructions, required flags and folder blueprint. Saves use the existing API version guards; service changes create a new immutable version for future drafts. Existing reviewed plans keep their snapshots. See [CLIENT_CUSTOMIZATION.md](CLIENT_CUSTOMIZATION.md) for backend setup, scope, authorization and client draft behavior.

Use next-action language and explicit owners when adapting the product to another service. Keep invitation access and delivery status separate. Recovery should identify the failed or uncertain operation while retaining confirmed resources. Label fixture/demo state wherever a connected workflow has not run. Long scope and answer text should remain readable, expandable and naturally wrapped.

## Local verification

Run the fixture from the project root with `node scripts/preview_fixture.mjs`, then open http://127.0.0.1:4318 (API 8318). The public synthetic operator account is `fixture@clientlaunch.example.com` / `preview`; the client code is `fixture-willow`. Restart resets the fixture's memory. No message or provider call is sent.

Run each heavy command separately after checking no other heavy project operation is active:

```powershell
# From apps/web, using existing dependencies
node_modules\.bin\tsc.CMD -b --pretty false
node_modules\.bin\vitest.CMD run --maxWorkers=1 --no-file-parallelism
node_modules\.bin\vite.CMD build --outDir ../../.runtime/theme-dist --emptyOutDir
# From the project root, with the fixture already running
node scripts/qa_themes.mjs
node scripts/qa_upgrade.mjs
.venv\Scripts\python.exe -m unittest discover -s tests/api -p "test_*.py"
.venv\Scripts\python.exe -m unittest discover -s tests/customization -p "test_*.py"
```

`qa_themes.mjs` launches an isolated headless Chrome profile and covers both appearances at 1440/390 and intermediate 1280/768 widths, OS changes, persistence, blocked storage, draft/error retention, menu/dialog focus and lack of extra business requests. Its read-only CSP probe uses the same public initialization files under `script-src 'self'`. `qa_upgrade.mjs` checks complete client/operator fixture journeys, including invalid invites, retries, versioned saves, files, receipts, signout and viewer permissions. Neither script attaches to the shared browser. Both reset fictional fixture data. Evidence is in `screenshots/theme-2026-10-07/` and its `journeys/` subfolder.

Docker remains unavailable. n8n, AI, connected providers and mail are not started or accepted by these checks. Fixture recovery records a pending operation without executing it. A production deployment still requires the established [runtime acceptance](RUNTIME_ACCEPTANCE.md) process. No live user database was changed.

## Public evidence

[Representative synthetic desktop/mobile screenshots](../screenshots/theme-2026-10-07/README.md) preserve both themes and client/operator views. Their [hash manifest](../screenshots/theme-2026-10-07/manifest.json) verifies exact source bytes. The source checkpoint passed 54 appearance checks and 26 journey checks with zero uncaught browser errors, 15 frontend tests and 22 API/customization tests. Local runtime receipts and rollback backups are private and excluded from publication. Git history records distributable source revisions.
