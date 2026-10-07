/** Local interaction fixture. No database, credentials, provider calls, n8n or outbound mail. */
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

const root = resolve(import.meta.dirname, '..');
const web = resolve(root, 'apps/web');
const apiPort = 8318, webPort = 4318;
const now = () => new Date().toISOString();
const tomorrow = () => new Date(Date.now() + 86400000).toISOString();
const sourceTemplates = JSON.parse(readFileSync(resolve(root, 'apps/api/templates.json'), 'utf8'));
let brand, templates, details, faults;
function reset() {
  brand = { agency_name: 'Northstar Studio', accent: '#183e32', welcome_heading: 'A thoughtful start. A confident launch.',
    welcome_message: 'Welcome to your project space. Share a few details, keep everything together, and let your team take care of the next step.',
    support_email: 'projects@northstar.example.com', version: 0 };
  templates = sourceTemplates.map((t, index) => ({ id: `template-${index}`, service_code: t.service_code, name: t.name,
    version: 1, description: `A repeatable beginning for ${t.name.toLowerCase()}.`, checklist: t.tasks.map(task => ({ ...task, description: 'Share approved project material. Use a secure channel for access; never paste a password.' })), folder_blueprint: t.folders, board_blueprint: ['To do', 'Done'] }));
  const clients = [['willow', 'Willow Harbor Studio', 'waiting_for_client'], ['cedar', 'Cedar & Finch', 'awaiting_approval'],
    ['atlas', 'Atlas Fieldwork', 'provisioning'], ['bloom', 'Bloom Supply Co.', 'ready'], ['orbit', 'Orbit House', 'handed_off'], ['studio', 'Studio Twenty Nine', 'waiting_for_client']];
  details = clients.map(([id, name, status], index) => {
    const checklist = templates[index % 2].checklist.map((task, i) => ({ ...task, id: `${id}-item-${i}`, status: status === 'ready' || status === 'handed_off' || (id === 'willow' && i < 2) ? 'completed' : 'open', client_visible: true, due_at: tomorrow(), owner_name: 'Maya Ellis', source: 'template' }));
    const active = ['waiting_for_client', 'ready', 'handed_off'].includes(status);
    return { onboarding: { id, client_name: name, client_email: `${id}@clients.example.com`, service_names: [templates[index % 2].name], status,
        substate: id === 'atlas' ? 'failed' : null, owner_name: 'Maya Ellis', created_at: now(), target_date: tomorrow(), workspace_name: 'Northstar Studio',
        project_name: name, portal_link: active ? `http://127.0.0.1:${webPort}/client?token=fixture-${id}` : undefined,
        connector_mode: 'fixture', invite_status: active ? 'active' : 'not_created', invite_expires_at: active ? tomorrow() : null },
      plan: { id: `${id}-plan`, revision: 1, status: status === 'awaiting_approval' ? 'pending' : 'approved', proposal_hash: 'fixture-plan-fingerprint',
        summary: `A considered ${templates[index % 2].name.toLowerCase()} for ${name}.`, deliverables: ['Review the agreed scope and launch priorities', 'Collect approved brand assets and content', 'Prepare a reviewed handoff for the delivery team'],
        missing_inputs: ['Approved content and project access contact'], risks: ['Confirm who can approve final content before kickoff.'], suggestions: [],
        welcome_draft: `Hello ${name},\n\nYour project space is ready. Please review the checklist and share the approved materials.\n\nThis welcome is fixture copy only. No message has been sent.` },
      deal: { approved_scope: 'A focused launch covering planning, approved content, visual design and delivery handoff.\n\nClient responsibilities: provide approved materials and nominate one decision maker. Changes to deliverables require review.\n\n' + 'This longer scope is included to verify readable detail wrapping and scrolling. '.repeat(12), proposal_text: 'Fictional approved scope; no contract is implied.' },
      checklist, operations: active ? [{ id: `${id}-drive`, system: 'drive', action: 'create_folder', status: 'succeeded', attempt_count: 1, external_id: `fixture-folder-${id}` }] : id === 'atlas' ? [
        { id: 'atlas-drive', system: 'drive', action: 'create_folder', status: 'succeeded', attempt_count: 1, external_id: 'fixture-folder-atlas' },
        { id: 'atlas-board', system: 'trello', action: 'create_board', status: 'failed', attempt_count: 1, error: 'Fixture board service temporarily unavailable. Existing folder is retained.' } ] : [],
      resources: active || id === 'atlas' ? [{ id: `${id}-folder`, system: 'drive', kind: 'folder', external_id: `fixture-folder-${id}`, name: `${name} · Project`, url: `/sim/fixture/${id}` }] : [],
      approvals: [], events: [{ id: `${id}-event`, kind: 'fixture_created', message: 'Fictional onboarding loaded. n8n has not run.', created_at: now() }], assets: [], submissions: [],
      welcome: active ? [{ id: `${id}-welcome`, recipient: `${id}@clients.example.com`, subject: `Welcome to ${name}`, body: 'Fixture welcome copy. No email delivery.', status: 'simulated_sent', created_at: now() }] : [], reminders: [],
      handoff: status === 'handed_off' ? { id: `${id}-handoff`, summary: 'Fixture handoff: approved scope and all required inputs reviewed.', created_at: now(), evidence: { submission_ids: [], asset_ids: [], resource_ids: [`${id}-folder`] } } : null };
  });
  faults = {};
}
reset();
function summarize(detail) {
  const required = detail.checklist.filter(item => item.required);
  return { ...detail.onboarding, required_complete: required.filter(item => item.status === 'completed').length, required_total: required.length,
    progress_percent: required.length ? Math.round(100 * required.filter(item => item.status === 'completed').length / required.length) : 0 };
}
function fail(status, detail) { throw Object.assign(new Error(detail), { status }); }
const server = createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-ClientLaunch-Fixture', 'true');
  try {
    const pathname = new URL(req.url, `http://127.0.0.1:${apiPort}`).pathname;
    // Small read-only CSP probe exercises the production pre-paint files without Vite's dev injection.
    if (req.method === 'GET' && pathname.startsWith('/api/fixture/theme-')) {
      res.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'");
      if (pathname === '/api/fixture/theme-probe') {
        res.setHeader('Content-Type', 'text/html; charset=utf-8');
        res.end('<!doctype html><html data-theme="dark"><head><meta name="theme-color" content="#0b1018"><link rel="stylesheet" href="/api/fixture/theme-css"><script src="/api/fixture/theme-js"></script></head><body>ClientLaunch theme initialization probe</body></html>'); return;
      }
      if (pathname === '/api/fixture/theme-js' || pathname === '/api/fixture/theme-css') {
        res.setHeader('Content-Type', pathname.endsWith('-js') ? 'text/javascript' : 'text/css');
        res.end(readFileSync(resolve(web, 'public', pathname.endsWith('-js') ? 'theme-init.js' : 'theme.css'))); return;
      }
    }
    const chunks = []; let bytes = 0;
    for await (const chunk of req) { bytes += chunk.length; if (bytes > 6 * 1024 * 1024) fail(413, 'Fixture request too large'); chunks.push(chunk); }
    const raw = Buffer.concat(chunks).toString('utf8');
    const body = raw && req.headers['content-type']?.includes('application/json') ? JSON.parse(raw) : {};
    const method = req.method;
    const role = /fixture_operator=(viewer|operator)/.exec(req.headers.cookie ?? '')?.[1];
    const user = { id: 'fixture-operator', email: 'fixture@clientlaunch.example.com', name: 'Maya Ellis', role: role ?? 'operator', workspace_id: 'fixture-workspace' };
    const session = { user, csrf_token: 'fixture-csrf' };
    let result;
    if (pathname.startsWith('/sim/fixture/')) { res.setHeader('Content-Type', 'text/plain'); res.end('Local fixture resource preview. No Drive or Trello resource exists.'); return; }
    if (pathname === '/api/health') result = { status: 'ok', mode: 'DEMO', connector_mode: 'fixture', fixture: true };
    else if (pathname === '/api/auth/login') {
      if (!['fixture@clientlaunch.example.com', 'viewer@clientlaunch.example.com'].includes(body.email) || body.password !== 'preview') fail(401, 'Use the public fixture account and password shown in the preview guide.');
      user.role = body.email.startsWith('viewer') ? 'viewer' : 'operator';
      res.setHeader('Set-Cookie', `fixture_operator=${user.role}; HttpOnly; SameSite=Lax; Path=/api`); result = session;
    } else if (pathname === '/api/auth/logout') { res.setHeader('Set-Cookie', 'fixture_operator=; Max-Age=0; Path=/api'); result = { ok: true }; }
    else if (pathname === '/api/fixture/reset' && method === 'POST') { reset(); result = { ok: true }; }
    else if (pathname === '/api/fixture/fault' && method === 'POST') { faults[body.path] = Number(body.count ?? 1); result = { ok: true }; }
    else if (pathname === '/api/client/exchange') {
      const id = String(body.portal_token ?? '').replace(/^fixture-/, '');
      if (!details.some(d => d.onboarding.id === id && d.onboarding.invite_status === 'active')) fail(401, 'This fixture invitation is invalid or expired. Use fixture-willow.');
      result = { token: `fixture-session-${id}`, expires_at: tomorrow() };
    } else if (pathname.startsWith('/api/client/')) {
      const id = (req.headers.authorization ?? '').replace(/^Bearer fixture-session-/, '');
      const d = details.find(detail => detail.onboarding.id === id); if (!d) fail(401, 'Client session expired');
      if (faults[pathname] > 0) { faults[pathname]--; fail(503, 'Fixture temporary failure. Your answer was not saved. Retry safely.'); }
      const intake = ['waiting_for_client', 'ready'].includes(d.onboarding.status) && !d.onboarding.substate;
      if (pathname === '/api/client/onboarding') result = { onboarding: { ...summarize(d), portal_link: undefined, client_email: undefined, intake_open: intake }, brand, checklist: d.checklist, assets: d.assets, submissions: d.submissions, next_actions: d.checklist.filter(item => item.status !== 'completed').sort((a,b) => Number(b.required) - Number(a.required)) };
      else if (!intake) fail(409, 'Intake is not open');
      else if (pathname === '/api/client/submissions') {
        if (!Array.isArray(body.answers) || !body.answers.length) fail(422, 'Choose a request and write an answer');
        for (const answer of body.answers) { const item = d.checklist.find(i => i.id === answer.checklist_item_id); if (!item || !String(answer.value).trim()) fail(422, 'Request unavailable'); item.status = 'completed'; }
        d.submissions.push({ id: randomUUID(), answers: body.answers, created_at: now() });
        d.events.push({ id: randomUUID(), kind: 'fixture_submission', message: 'Fixture answer recorded immediately. n8n processing is not exercised.', created_at: now() }); result = { received: true };
      } else if (pathname === '/api/client/assets') {
        const filename = /filename="([^"\r\n]+)"/.exec(raw)?.[1];
        const itemId = /name="checklist_item_id"\r\n\r\n([^\r\n]+)/.exec(raw)?.[1];
        const item = d.checklist.find(i => i.id === itemId); if (!filename || !item) fail(422, 'File or related request unavailable');
        if (!/\.(png|jpe?g|pdf)$/i.test(filename)) fail(422, 'Use PNG, JPG or PDF');
        d.assets.push({ id: randomUUID(), filename, checklist_item_id: itemId, created_at: now() }); item.status = 'completed'; result = { received: true, fixture_metadata_only: true };
      } else fail(404, 'Fixture route unavailable');
      if (d.checklist.filter(i => i.required).every(i => i.status === 'completed') && d.onboarding.status === 'waiting_for_client') d.onboarding.status = 'ready';
    } else {
      if (!role) fail(401, 'Operator login required');
      if (method !== 'GET') { if (role === 'viewer') fail(403, 'Operator role required'); if (req.headers['x-csrf-token'] !== 'fixture-csrf') fail(403, 'CSRF token required'); }
      if (faults[pathname] > 0) { faults[pathname]--; fail(503, 'Fixture temporary failure. Your edits are retained.'); }
      if (pathname === '/api/auth/me') result = session;
      else if (pathname === '/api/onboardings') result = { items: details.map(summarize) };
      else if (pathname === '/api/workspace/brand') {
        if (method === 'PATCH') { if (body.expected_version !== brand.version) fail(409, 'Brand settings changed. Reload before saving.'); const { expected_version, ...fields } = body; brand = { ...fields, version: expected_version + 1 }; }
        result = brand;
      } else if (pathname === '/api/templates') result = { items: templates };
      else if (pathname.startsWith('/api/templates/')) {
        const template = templates.find(t => t.service_code === decodeURIComponent(pathname.split('/').at(-1))); if (!template) fail(404, 'Service template unavailable');
        if (body.expected_version !== template.version) fail(409, 'Template changed. Reload before saving.');
        if (!body.name?.trim() || !body.checklist?.length || new Set(body.checklist.map(i => i.key)).size !== body.checklist.length || !body.folder_blueprint?.length || body.folder_blueprint.some(f => /[\\/]/.test(f)) || new Set(body.folder_blueprint.map(f => f.toLowerCase())).size !== body.folder_blueprint.length) fail(422, 'Use a service name, unique requests and unique folder names without slashes.');
        Object.assign(template, { ...body, version: template.version + 1, id: randomUUID() }); delete template.expected_version; result = template;
      } else if (pathname.startsWith('/api/onboardings/')) {
        const [, , , id, action] = pathname.split('/'); const d = details.find(detail => detail.onboarding.id === id); if (!d) fail(404, 'Onboarding unavailable');
        if (!action) result = { ...d, onboarding: summarize(d) };
        else if (action === 'state') { if (body.action === 'pause') { d.onboarding.previous_status = d.onboarding.status; d.onboarding.status = 'paused'; } else d.onboarding.status = d.onboarding.previous_status ?? 'waiting_for_client'; result = { status: d.onboarding.status }; }
        else if (action === 'recover') { const operation = d.operations.find(op => op.id === body.operation_id); if (!operation || operation.status !== 'failed') fail(409, 'Inspect the operation before retrying'); operation.status = 'pending'; d.onboarding.substate = 'recovering'; result = { fixture: true, queued: true }; }
        else if (action === 'handoff') { if (d.onboarding.status !== 'ready') fail(409, 'Complete required inputs before handoff'); d.handoff = { id: randomUUID(), summary: body.summary, created_at: now(), evidence: { submission_ids: d.submissions.map(s => s.id), asset_ids: d.assets.map(a => a.id), resource_ids: d.resources.map(r => r.id) } }; d.onboarding.status = 'handed_off'; result = d.handoff; }
        else fail(501, 'This fixture does not run n8n. Use native API tests for workflow and provisioning behavior.');
      } else fail(404, 'Fixture route unavailable');
    }
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(result));
  } catch (error) { res.statusCode = error.status ?? 400; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ detail: error.status ? error.message : 'Invalid fixture request' })); }
});
let vite;
server.on('error', error => { console.error(`Fixture API could not start: ${error.message}`); process.exitCode = 1; vite?.kill(); });
server.listen(apiPort, '127.0.0.1', () => {
  console.log(`Local fixture API: http://127.0.0.1:${apiPort} (memory only; no n8n/providers/email)`);
  console.log('Public fixture login: fixture@clientlaunch.example.com / preview; client code: fixture-willow');
  if (!process.argv.includes('--api-only')) {
    vite = spawn(process.execPath, [resolve(web, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', String(webPort), '--strictPort'],
      { cwd: web, env: { ...process.env, VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` }, windowsHide: true, stdio: 'inherit' });
    vite.on('exit', code => { if (code) process.exitCode = code; server.close(); });
  }
});
function stop() { vite?.kill(); server.close(() => process.exit()); }
process.on('SIGINT', stop); process.on('SIGTERM', stop);
