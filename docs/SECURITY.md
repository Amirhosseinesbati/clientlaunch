# Security model and release checks

**Status:** controls described here are source-level observations or release requirements. They have not all passed penetration or runtime testing. This pilot should not hold real client data until the pending checks below are complete.

## Trust boundaries

The browser is untrusted and reaches the business API only. n8n and the AI service use internal server-to-server authentication. Won-deal events arrive over an externally exposed webhook and require an HMAC over canonical JSON before schema processing. Client proposals, answers, uploads and model/tool output remain data, never authority to modify system instructions or purchased scope. Connected provider credentials stay server-side in n8n/customer secret storage; workflow exports must be reviewed for credential names, IDs, headers and environment-specific URLs.

## Implemented source-level controls observed 2026-09-28

- Operator passwords use Argon2 hashes. Sessions are stored as token digests with expiry and revocation. Browser cookie is HttpOnly, SameSite=Lax and uses a CSRF token for state-changing cookie-authenticated calls. `COOKIE_SECURE=true` is required under deployment TLS.
- Viewer-role onboarding detail redacts the bearer-like client portal link and the recorded welcome body that contains it. A viewer can inspect progress without acquiring a client submission token.
- Roles include admin/operator/viewer; write routes use the operator role dependency. List/detail requests constrain the operator workspace. Viewer detail removes `portal_link` and the welcome body, which may embed the client token; an API regression test passed. Client invite exchange yields an expiring session for one onboarding; client reads and uploads are scoped to that onboarding.
- Approval compares the current plan revision and proposal hash, checks expiry and consumes a pending approval atomically. A new plan cannot silently reuse old approval.
- The signed event has per-workspace event/deal uniqueness and rejects same-ID conflicting payloads. Provisioning has unique operation/idempotency keys and an explicit uncertain outcome path.
- Card claims compare expected status and idempotency key with current state, so a stale workflow snapshot cannot start the wrong provider write. Concurrent client edits retain an already claimed or unknown card write until its provider outcome is reconciled, then schedule a later update if required. Connected board reconciliation requires a verified To Do list ID before cards can be created.
- Uploads are limited to 5 MiB and PNG, JPEG or PDF by declared MIME plus leading signature, with server-generated storage name under workspace/onboarding directories. File downloads recheck operator or client scope.

These are code-reading observations, not an assertion that all adversarial cases pass. In particular, file signatures are a first check rather than deep malware/PDF parsing. The frontend must escape or sanitize untrusted text rather than render raw HTML.

## Configuration that must change outside DEMO

Python retains convenience fallbacks only for the local DEMO. Connected mode now refuses startup unless `APP_MODE=CONNECTED`, `MODEL_MODE=connected`, distinct non-demo `INTERNAL_KEY` and `WEBHOOK_SECRET` values of at least 32 characters, and `COOKIE_SECURE=true`. Five isolated startup tests pass for weak secret, insecure cookie, repeated secret, demo model and valid connected settings; these do not verify deployment TLS or external credentials. `compose.yaml` now passes `APP_MODE`, `COOKIE_SECURE` and `CORS_ORIGINS` to the API, with declarations in `.env.example`; `docker compose config --quiet` passed, while connected container startup remains untested. The installer must still supply unique random values and verify HTTPS, narrow CORS origins, a protected n8n admin surface, distinct DB roles, least-privilege provider credentials and a fixed Drive/Trello destination. No API or n8n admin credential belongs in browser JavaScript. Do not log bearer tokens, signatures, invite links or proposal bodies.

The signing and asset paths must be reviewed for path traversal, ID guessing and cross-workspace access. Rate limits for login, webhook, invite exchange and uploads are a deployment requirement. Add reverse-proxy request size limits, outbound network allowlisting and n8n SSRF protection where applicable. Source and model text may contain prompt-injection instructions; the AI service must preserve only evidence-backed draft items and the API must reject unpurchased service codes.

## Adversarial release tests

| Test | Required outcome | Current evidence |
|---|---|---|
| Missing/bad event HMAC, wrong schema, same event ID with different body | 401/422/409; no state mutation | Invalid HMAC 401 and same-ID conflict 409 observed through local n8n; wrong-schema and mutation audit pending |
| Cross-workspace operator detail, asset, approval and export attempts | 404/403; no leaked content | API isolation tests passed; full adversarial/browser review pending |
| Viewer detail containing client invite token | No portal link or token-bearing welcome body | Source redaction and API regression test passed; latest container runtime pending |
| Client token for a second onboarding; revoked/expired invite | Denied; no alternate record | Pending runtime |
| Duplicate/stale/expired approval or changed plan hash | Denied; no side effects | Pending runtime |
| Concurrent provisioning/card claims and ambiguous provider timeout | One known external resource or uncertain reconciliation; stale card claims denied | Targeted local card-concurrency and connected-board-reconcile tests passed; provider runtime pending |
| Executable/oversize/misdeclared upload and asset path abuse | Denied; no executable stored | Pending runtime |
| Malicious proposal text requesting system override | No policy/connector change; unsupported item flagged for review | Pending connected model test |
| CSV/HTML/Markdown injection in exports/views | Escaped or sanitized | Pending UI/export review |

## Secret, data and license handling

Keep `.env`, n8n credential database and encryption key out of version control and backups in a protected location. Redact n8n execution payloads and optional model traces, and define customer retention/deletion rules. n8n warns that [workflow exports can expose credential names/IDs and HTTP headers](https://docs.n8n.io/build/manage-workflows/export-and-import). The n8n [Sustainable Use License](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) sets restrictions on use/distribution; this repository should be evaluated as a customer-specific workflow/service pack, with any redistribution or hosted n8n offering reviewed separately. This paragraph is an operational constraint, not legal advice.
