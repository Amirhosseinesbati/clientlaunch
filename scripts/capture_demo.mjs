/**
 * Read-only visual evidence for the local synthetic DEMO.
 * Usage: node scripts/capture_demo.mjs --onboarding UUID --phase after-approval [--client]
 * Login and optional client token exchange create sessions; no business mutations occur.
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, isAbsolute, join, resolve, sep } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const defaults = {
  base: 'http://127.0.0.1:8080',
  chrome: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  out: resolve(root, 'screenshots'),
  phase: 'demo',
};
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const privateValues = [];
const debug = (message) => { if (process.env.CLIENTLAUNCH_CAPTURE_DEBUG === '1') console.error(`[capture] ${message}`); };

function optionArgs(argv) {
  const options = { ...defaults, client: false, tab: 'plan' };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (key === '--client') { options.client = true; continue; }
    if (!['--onboarding', '--phase', '--tab', '--base', '--chrome', '--out'].includes(key) || !argv[index + 1]) {
      throw new Error('Usage: node scripts/capture_demo.mjs --onboarding UUID --phase LABEL [--tab plan|resources|activity|checklist|handoff] [--client] [--base http://127.0.0.1:8080] [--out screenshots]');
    }
    options[key.slice(2)] = argv[++index];
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(options.onboarding ?? '')) {
    throw new Error('--onboarding must be a UUID from the local DEMO.');
  }
  if (!/^[a-z0-9][a-z0-9_-]{0,49}$/i.test(options.phase)) {
    throw new Error('--phase must contain 1–50 letters, digits, underscores, or hyphens.');
  }
  if (!['plan', 'resources', 'activity', 'checklist', 'handoff'].includes(options.tab)) {
    throw new Error('--tab must be plan, resources, activity, checklist, or handoff.');
  }
  const url = new URL(options.base);
  if (url.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('--base must be a plain local HTTP origin.');
  }
  options.base = url.origin;
  options.out = isAbsolute(options.out) ? options.out : resolve(root, options.out);
  if (!existsSync(options.chrome)) throw new Error('Chrome executable was not found; use --chrome PATH.');
  return options;
}

function envPassword() {
  const envPath = resolve(root, '.env');
  if (!existsSync(envPath)) throw new Error('The ignored .env is missing; run node scripts/demo.mjs first.');
  const match = readFileSync(envPath, 'utf8').match(/^DEMO_ADMIN_PASSWORD=(.*)$/m);
  if (!match?.[1] || match[1] === 'REPLACE_WITH_RANDOM') throw new Error('DEMO_ADMIN_PASSWORD is not configured in .env.');
  privateValues.push(match[1]);
  return match[1];
}

async function localJson(url, init = {}) {
  const response = await fetch(url, { ...init, signal: AbortSignal.timeout(7000) });
  if (!response.ok) throw new Error(`Local API ${new URL(url).pathname} returned HTTP ${response.status}.`);
  return { response, body: await response.json() };
}

async function authorize(options) {
  const health = await localJson(`${options.base}/api/health`);
  if (health.body.mode !== 'DEMO' || health.body.connector_mode !== 'demo') {
    throw new Error('Screenshot capture is limited to the local DEMO with simulated connectors.');
  }
  const login = await localJson(`${options.base}/api/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'operator@northstar.example.com', password: envPassword() }),
  });
  const setCookie = login.response.headers.getSetCookie().find((item) => item.startsWith('clientlaunch_session='));
  const session = setCookie?.split(';', 1)[0]?.slice('clientlaunch_session='.length);
  if (!session) throw new Error('The local DEMO login did not return an operator session cookie.');
  privateValues.push(session);
  const detail = await localJson(`${options.base}/api/onboardings/${options.onboarding}`, {
    headers: { Cookie: `clientlaunch_session=${session}` },
  });
  const name = detail.body?.onboarding?.client_name;
  if (!name) throw new Error('The selected onboarding has no client name.');
  let portalUrl;
  if (options.client) {
    const link = detail.body.onboarding.portal_link;
    if (!link) throw new Error('This onboarding has no client portal link yet.');
    const parsed = new URL(link);
    const portalToken = parsed.searchParams.get('token');
    if (parsed.pathname !== '/client' || !portalToken) throw new Error('The client portal link is invalid.');
    privateValues.push(portalToken);
    portalUrl = new URL('/client', options.base);
    portalUrl.searchParams.set('token', portalToken);
  }
  return { session, name, portalUrl, proposalHash: detail.body.plan?.proposal_hash };
}

function safeRemoveTemp(directory) {
  if (!directory || !existsSync(directory)) return;
  const actual = realpathSync(directory);
  const tempRoot = realpathSync(tmpdir());
  if (!actual.startsWith(`${tempRoot}${sep}`) || !basename(actual).startsWith('clientlaunch-shot-')) {
    throw new Error('Refusing to remove a browser profile outside the dedicated temporary directory.');
  }
  rmSync(actual, { recursive: true, force: true });
}

async function launchChrome(options) {
  const profile = mkdtempSync(join(tmpdir(), 'clientlaunch-shot-'));
  const child = spawn(options.chrome, [
    '--headless=new', '--no-first-run', '--no-default-browser-check',
    '--disable-background-networking', '--disable-extensions', '--disable-sync', '--disable-gpu',
    // The local Windows headless renderer otherwise crashes in DawnGraphite/GPU sandbox.
    '--disable-features=DawnGraphite,Graphite', '--disable-gpu-sandbox', '--no-sandbox',
    '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
    '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
  ], { stdio: 'ignore', windowsHide: true });
  let launchError;
  child.once('error', (error) => { launchError = error; });
  child.once('exit', (code, signal) => { debug(`Chrome exited (${code ?? signal})`); });
  const portFile = join(profile, 'DevToolsActivePort');
  try {
    const deadline = Date.now() + 12000;
    while (Date.now() < deadline) {
      if (launchError) throw launchError;
      if (child.exitCode !== null) throw new Error(`Chrome exited early (${child.exitCode}).`);
      if (existsSync(portFile)) {
        const port = Number(readFileSync(portFile, 'utf8').split(/\r?\n/, 1)[0]);
        if (!Number.isInteger(port) || port <= 0) throw new Error('Chrome returned an invalid debugging port.');
        const response = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
          method: 'PUT', signal: AbortSignal.timeout(3000),
        });
        if (!response.ok) throw new Error(`Chrome DevTools target creation returned HTTP ${response.status}.`);
        const target = await response.json();
        if (!target.webSocketDebuggerUrl) throw new Error('Chrome did not expose a page DevTools endpoint.');
        debug('Chrome page target ready');
        return { child, profile, wsUrl: target.webSocketDebuggerUrl };
      }
      await sleep(150);
    }
    throw new Error('Chrome did not expose DevTools within 12 seconds.');
  } catch (error) {
    if (child.exitCode === null) child.kill();
    try { safeRemoveTemp(profile); } catch { /* Retain profile if Chrome still holds it. */ }
    throw error;
  }
}

class DevTools {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    ws.addEventListener('message', (event) => {
      let data;
      try { data = JSON.parse(String(event.data)); } catch { return; }
      if (!data.id) return;
      const call = this.pending.get(data.id);
      if (!call) return;
      this.pending.delete(data.id);
      clearTimeout(call.timer);
      if (data.error) call.reject(new Error(`Chrome DevTools ${call.method}: ${data.error.message}`));
      else call.resolve(data.result ?? {});
    });
    ws.addEventListener('close', (event) => {
      debug(`DevTools closed (${event.code})`);
      for (const call of this.pending.values()) { clearTimeout(call.timer); call.reject(new Error(`Chrome DevTools connection closed during ${call.method}.`)); }
      this.pending.clear();
    });
  }

  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((resolveOpen, rejectOpen) => {
      const timer = setTimeout(() => rejectOpen(new Error('Chrome DevTools WebSocket timed out.')), 5000);
      ws.addEventListener('open', () => { clearTimeout(timer); resolveOpen(); }, { once: true });
      ws.addEventListener('error', () => { clearTimeout(timer); rejectOpen(new Error('Chrome DevTools WebSocket failed.')); }, { once: true });
    });
    return new DevTools(ws);
  }

  send(method, params = {}, timeout = 10000) {
    const id = this.nextId++;
    debug(`CDP ${method}`);
    return new Promise((resolveCall, rejectCall) => {
      const timer = setTimeout(() => { this.pending.delete(id); rejectCall(new Error(`Chrome DevTools ${method} timed out.`)); }, timeout);
      this.pending.set(id, { method, resolve: resolveCall, reject: rejectCall, timer });
      try { this.ws.send(JSON.stringify({ id, method, params })); }
      catch (error) { clearTimeout(timer); this.pending.delete(id); rejectCall(error); }
    });
  }

  async evaluate(expression) {
    const output = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (output.exceptionDetails) throw new Error('The browser page script failed during screenshot capture.');
    return output.result?.value;
  }

  async waitFor(expression, label, timeout = 18000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      if (await this.evaluate(expression)) return;
      await sleep(180);
    }
    throw new Error(`Timed out waiting for ${label}.`);
  }
}

async function pageReady(cdp, url, selector, label) {
  await cdp.send('Page.navigate', { url: url.href ?? String(url) });
  await cdp.waitFor(`Boolean(document.querySelector(${JSON.stringify(selector)}))`, label);
  await cdp.evaluate('document.fonts.ready.then(() => true)');
  await sleep(200);
}

async function screenshot(cdp, path) {
  const result = await cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false }, 15000);
  const bytes = Buffer.from(result.data ?? '', 'base64');
  if (bytes.length < 1000 || bytes.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') {
    throw new Error('Chrome returned an invalid or empty PNG.');
  }
  writeFileSync(path, bytes);
  console.log(`Saved ${path}`);
}

async function capture(options, auth) {
  const browser = await launchChrome(options);
  let cdp;
  try {
    cdp = await DevTools.connect(browser.wsUrl);
    debug('DevTools connected');
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Network.enable');
    const cookie = await cdp.send('Network.setCookie', {
      name: 'clientlaunch_session', value: auth.session, url: `${options.base}/api/`,
      path: '/api', httpOnly: true, sameSite: 'Lax', secure: false,
    });
    if (!cookie.success) throw new Error('Could not add the local operator session to Chrome.');
    mkdirSync(options.out, { recursive: true });
    for (const width of [1440, 1024, 390]) {
      const height = width === 390 ? 844 : 900;
      await cdp.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width === 390 });
      const operatorUrl = new URL('/', options.base);
      operatorUrl.searchParams.set('onboarding', options.onboarding);
      await pageReady(cdp, operatorUrl, '.workspace-shell .sidebar-nav', 'operator overview');
      await screenshot(cdp, join(options.out, `${options.phase}-overview-${width}.png`));

      const clickedNav = await cdp.evaluate("(() => { const button = [...document.querySelectorAll('.sidebar-nav button')].find(item => item.textContent?.includes('Onboardings')); if (!button) return false; button.click(); return true; })()");
      if (!clickedNav) throw new Error('The Onboardings navigation button was not found.');
      await cdp.waitFor("Boolean(document.querySelector('.onboarding-row.row-selected'))", 'selected onboarding row');
      const clickedRow = await cdp.evaluate("(() => { const row = document.querySelector('.onboarding-row.row-selected'); if (!row) return false; row.click(); return true; })()");
      if (!clickedRow) throw new Error('The selected onboarding row could not be opened.');
      const selectedId = await cdp.evaluate("new URLSearchParams(location.search).get('onboarding')");
      if (selectedId !== options.onboarding) throw new Error('The UI selected a different onboarding ID.');
      await cdp.waitFor(`Boolean(document.querySelector('.detail-open .detail-panel .detail-header')?.textContent?.includes(${JSON.stringify(auth.name)}))`, 'onboarding detail');
      if (auth.proposalHash) {
        await cdp.waitFor(`Boolean(document.querySelector('.detail-open .plan-summary-card code')?.textContent?.includes(${JSON.stringify(auth.proposalHash.slice(0, 12))}))`, 'matching plan fingerprint');
      }
      if (options.tab !== 'plan') {
        const tabLabel = options.tab[0].toUpperCase() + options.tab.slice(1);
        const clickedTab = await cdp.evaluate(`(() => { const tab = [...document.querySelectorAll('.detail-open [role="tab"]')].find(item => item.textContent?.includes(${JSON.stringify(tabLabel)})); if (!tab) return false; tab.click(); return true; })()`);
        if (!clickedTab) throw new Error(`The ${tabLabel} tab was not found.`);
        await cdp.waitFor(`Boolean([...document.querySelectorAll('.detail-open [role="tab"]')].find(item => item.textContent?.includes(${JSON.stringify(tabLabel)}) && item.getAttribute('aria-selected') === 'true'))`, `${tabLabel} tab`);
      }
      await sleep(200);
      await screenshot(cdp, join(options.out, `${options.phase}-detail-${width}.png`));
    }
    if (options.client && auth.portalUrl) {
      await cdp.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
      await pageReady(cdp, auth.portalUrl, '.client-portal .client-hero', 'scoped client portal');
      await screenshot(cdp, join(options.out, `${options.phase}-client-390.png`));
    }
  } finally {
    if (cdp) {
      try { await cdp.send('Browser.close', {}, 2000); } catch { /* Chrome may close before replying. */ }
      cdp.ws.close();
    }
    if (browser.child.exitCode === null) browser.child.kill();
    await sleep(200);
    try { safeRemoveTemp(browser.profile); } catch { /* Windows may release Chrome's profile shortly after exit. */ }
  }
}

try {
  const options = optionArgs(process.argv.slice(2));
  const auth = await authorize(options);
  await capture(options, auth);
} catch (error) {
  let message = error instanceof Error ? error.message : String(error);
  for (const value of privateValues) message = message.replaceAll(value, '[redacted]');
  console.error(`Screenshot capture failed: ${message}`);
  process.exitCode = 1;
}
