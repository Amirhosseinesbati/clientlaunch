/** Isolated headless checks against the local fixture only. Never attaches to a shared browser. */
import { spawn } from 'node:child_process';
import { existsSync, readFileSync, mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import assert from 'node:assert/strict';

const base = 'http://127.0.0.1:4318';
const out = resolve(import.meta.dirname, '../screenshots/theme-2026-10-07/journeys');
const profile = mkdtempSync(join(tmpdir(), 'clientlaunch-qa-'));
const checks = [], errors = [];
const sleep = ms => new Promise(done => setTimeout(done, ms));
const health = await fetch(`${base}/api/health`).then(r => r.json());
assert.equal(health.fixture, true, 'QA is restricted to the local fixture.');
await fetch(`${base}/api/fixture/reset`, { method: 'POST' });
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', ['--headless=new', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--disable-extensions', '--disable-sync', '--disable-gpu', '--disable-features=DawnGraphite,Graphite', '--disable-gpu-sandbox', '--no-sandbox',
  '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
let ws;
try {
  const portFile = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 80 && !existsSync(portFile); i++) { if (chrome.exitCode !== null) throw new Error('Headless Chrome exited early'); await sleep(150); }
  const port = Number(readFileSync(portFile, 'utf8').split(/\r?\n/)[0]);
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' }).then(r => r.json());
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((done, reject) => { ws.addEventListener('open', done, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  let counter = 0;
  const pending = new Map();
  ws.addEventListener('message', event => {
    const data = JSON.parse(String(event.data));
    if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
    if (!data.id) return;
    const call = pending.get(data.id); if (!call) return;
    clearTimeout(call.timer); pending.delete(data.id); data.error ? call.reject(new Error(data.error.message)) : call.resolve(data.result);
  });
  function send(method, params = {}) { return new Promise((resolveCall, reject) => { const id = ++counter; const timer = setTimeout(() => reject(new Error(`${method} timed out`)), 15000); pending.set(id, { resolve: resolveCall, reject, timer }); ws.send(JSON.stringify({ id, method, params })); }); }
  async function evaluate(expression) { const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? 'Browser evaluation failed'); return r.result.value; }
  async function wait(expression, label) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await sleep(100); } throw new Error(`Waiting for ${label}`); }
  async function navigate(path) { await send('Page.navigate', { url: base + path }); }
  async function input(selector, value) { await evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el) throw Error('Input not found'); const prototype=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype,'value').set.call(el,${JSON.stringify(value)}); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); })()`); }
  async function click(selector) { await evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el || el.disabled) throw Error('Control not available: '+${JSON.stringify(selector)}); el.click(); })()`); await sleep(150); }
  async function clickText(selector, text) { await evaluate(`(() => { const el=[...document.querySelectorAll(${JSON.stringify(selector)})].find(e=>e.textContent.includes(${JSON.stringify(text)})); if(!el || el.disabled) throw Error('Control not available: '+${JSON.stringify(text)}); el.click(); })()`); await sleep(150); }
  async function viewport(width) { await send('Emulation.setDeviceMetricsOverride', { width, height: width < 500 ? 844 : 1000, deviceScaleFactor: 1, mobile: width < 500 }); }
  async function shot(name) { await sleep(200); const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); writeFileSync(join(out, `${name}.png`), Buffer.from(r.data, 'base64')); }
  async function check(label, expression) { assert.equal(await evaluate(expression), true, label); checks.push(label); console.log(`PASS ${label}`); }
  async function fault(path) { await fetch(`${base}/api/fixture/fault`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) }); }
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('Network.setBlockedURLs', { urls: ['*fonts.googleapis.com*', '*fonts.gstatic.com*'] });
  mkdirSync(out, { recursive: true });
  await viewport(1440); await navigate('/'); await wait("Boolean(document.querySelector('#email'))", 'login');
  await input('#email', 'fixture@clientlaunch.example.com'); await input('#password', 'preview'); await click('.auth-submit');
  await wait("Boolean(document.querySelector('.onboarding-row'))", 'operator workspace');
  await check('Fixture state is visible', "document.body.textContent.includes('Local fixture.')");
  await shot('operator-desktop');
  await clickText('.sidebar-nav button', 'Onboardings'); await click('.onboarding-row'); await wait("Boolean(document.querySelector('.detail-header'))", 'detail');
  await clickText('[role=tab]', 'Invitation'); await wait("Boolean(document.querySelector('#invite-link'))", 'invitation');
  await check('Invitation distinguishes simulated mail', "document.body.textContent.includes('Simulated only') && document.querySelector('#invite-link').value.includes('fixture-willow')");
  await shot('invitation-desktop');
  await clickText('.sidebar-nav button', 'Templates & brand'); await wait("Boolean(document.querySelector('#agency-name'))", 'brand editor');
  await input('#agency-name', 'Harbor & Co.'); await input('#welcome-heading', 'Your next chapter starts here.');
  await fault('/api/workspace/brand'); await clickText('.settings-card button', 'Save brand'); await wait("document.body.textContent.includes('Settings not saved')", 'save failure');
  await check('Failed brand save keeps edits', "document.querySelector('#agency-name').value === 'Harbor & Co.'");
  await clickText('.settings-card button', 'Save brand'); await wait("document.body.textContent.includes('Brand settings saved')", 'brand saved');
  await check('Repeated save is disabled after success', "[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Save brand')).disabled");
  await shot('brand-desktop');
  await clickText('.settings-switch button', 'Service templates'); await wait("Boolean(document.querySelector('#template-name'))", 'template editor');
  await input('#template-name', 'Website launch · tailored'); await clickText('.template-editor button', 'Save new version');
  await wait("document.body.textContent.includes('Version 2')", 'new version'); await check('Versioned template save is recorded', "document.querySelector('#template-name').value.includes('tailored')"); await shot('templates-desktop');
  await navigate('/client'); await wait("Boolean(document.querySelector('#portal-token'))", 'client access');
  await input('#portal-token', `${base}/client?token=not-a-real-invite`); await clickText('button', 'Open my project');
  await wait("document.querySelector('.error-state')?.textContent.includes('invalid')", 'invalid invitation');
  await input('#portal-token', `${base}/client?token=fixture-willow`); await clickText('button', 'Open my project');
  await wait("Boolean(document.querySelector('.client-portal'))", 'client project');
  await check('Saved brand reaches scoped client portal', "document.querySelector('.client-brand').textContent.includes('Harbor & Co.') && document.querySelector('.client-hero h1').textContent.includes('next chapter')");
  await check('Token is absent from browser address', "!location.search.includes('token')");
  await shot('client-desktop');
  await clickText('button', 'Start this request'); await wait("document.activeElement.id === 'answer-text'", 'answer focus');
  const itemId = await evaluate("document.querySelector('#answer-item').value");
  await input('#answer-text', 'Domain is with our IT contact. Please request delegated access through the secure channel.');
  const otherId = await evaluate(`([...document.querySelector('#answer-item').options].find(o=>o.value && o.value!==${JSON.stringify(itemId)})).value`);
  await input('#answer-item', otherId); await check('New request does not inherit another answer draft', "document.querySelector('#answer-text').value === ''");
  await input('#answer-text', 'We are available Tuesday at 10:00 UTC.'); await input('#answer-item', itemId);
  await check('Switching requests restores the correct draft', "document.querySelector('#answer-text').value.includes('IT contact')");
  await navigate('/client'); await wait("Boolean(document.querySelector('#answer-text'))", 'reload draft');
  await check('Draft survives reload and stays with its request', `document.querySelector('#answer-text').value.includes('IT contact') && document.querySelector('#answer-item').value === ${JSON.stringify(itemId)}`);
  await fault('/api/client/submissions'); await clickText('button', 'Send answer'); await wait("document.body.textContent.includes('Answer not sent')", 'failed answer');
  await check('Failed answer keeps draft', "document.querySelector('#answer-text').value.includes('IT contact')");
  await shot('client-submit-error');
  await clickText('button', 'Send answer'); await wait("document.body.textContent.includes('Answer received')", 'successful retry');
  await check('Successful answer clears its draft', "document.querySelector('#answer-text').value === ''");
  await check('Submission receipt is visible after acceptance', "document.querySelector('.client-received-inputs').textContent.includes('IT contact')");
  await evaluate("(() => {const data=new DataTransfer();data.items.add(new File(['text'],'invalid.txt',{type:'text/plain'}));const input=document.querySelector('#asset-file');input.files=data.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()");
  await wait("document.body.textContent.includes('Choose another file')", 'unsupported file');
  await check('Unsupported file is rejected before upload', "[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Upload file')).disabled");
  await input('#asset-item', otherId);
  await evaluate("(() => {const data=new DataTransfer();data.items.add(new File(['%PDF-1.4 fixture'],'reference.pdf',{type:'application/pdf'}));const input=document.querySelector('#asset-file');input.files=data.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()");
  await clickText('button','Upload file'); await wait("document.body.textContent.includes('File received')", 'fixture upload');
  await check('File receipt and reset are visible', "document.querySelector('.client-files-card').textContent.includes('reference.pdf') && document.querySelector('#asset-file').files.length===0");
  await viewport(390); await evaluate('window.scrollTo(0,0)'); await shot('client-mobile');
  await check('Client mobile has no horizontal overflow', 'document.documentElement.scrollWidth <= innerWidth');
  await click('.client-signout'); await wait("Boolean(document.querySelector('#portal-token'))", 'signed out');
  await check('Sign out clears client token and draft', "sessionStorage.getItem('clientlaunch_client_session') === null && sessionStorage.getItem('clientlaunch_draft_willow') === null");
  await navigate('/'); await wait("Boolean(document.querySelector('.sidebar-nav'))", 'operator mobile');
  await click('.mobile-menu-button'); await clickText('.sidebar-nav button', 'Onboardings'); await click('.onboarding-row');
  await wait("Boolean(document.querySelector('[role=dialog]'))", 'mobile dialog');
  await check('Mobile detail has accessible dialog semantics', "document.querySelector('[role=dialog]').getAttribute('aria-modal') === 'true'");
  await clickText('[role=tab]', 'Invitation'); await evaluate("document.querySelector('[role=tab][aria-selected=true]').focus()"); await send('Input.dispatchKeyEvent', { type:'keyDown', key:'ArrowLeft', code:'ArrowLeft', windowsVirtualKeyCode:37 });
  await check('Detail tabs support arrow-key navigation', "document.activeElement.getAttribute('role') === 'tab' && document.activeElement.getAttribute('aria-selected') === 'true' && document.activeElement.textContent.includes('Resources')");
  await clickText('[role=tab]', 'Plan'); await click('.scope-disclosure summary'); await shot('detail-mobile');
  await check('Mobile detail has no horizontal overflow', 'document.documentElement.scrollWidth <= innerWidth');
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await wait("!document.querySelector('.detail-open')", 'escape close'); checks.push('Escape closes mobile details');
  await click('.mobile-menu-button'); await clickText('.sidebar-nav button', 'Templates & brand'); await wait("Boolean(document.querySelector('#agency-name'))", 'mobile settings'); await shot('brand-mobile');
  await check('Mobile settings has no horizontal overflow', 'document.documentElement.scrollWidth <= innerWidth');
  await viewport(1440); await evaluate("fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'viewer@clientlaunch.example.com',password:'preview'})}).then(r=>r.ok)");
  await navigate('/'); await wait("Boolean(document.querySelector('.sidebar-nav'))", 'viewer workspace'); await clickText('.sidebar-nav button','Templates & brand'); await wait("Boolean(document.querySelector('#agency-name'))", 'viewer brand');
  await check('Viewer customization is read-only', "document.querySelector('.settings-card fieldset').disabled && [...document.querySelectorAll('button')].find(b=>b.textContent.includes('Save brand')).disabled");
  await navigate('/client?token=fixture-orbit'); await wait("Boolean(document.querySelector('.client-portal'))", 'closed project');
  await check('Handed-off project closes client input controls', "document.querySelector('#answer-text').disabled && document.querySelector('#asset-file').disabled && document.body.textContent.includes('closed')");
  await click('.client-signout'); await wait("Boolean(document.querySelector('#portal-token'))", 'signed out again');
  await input('#portal-token','fixture-orbit'); await clickText('button','Open my project'); await wait("Boolean(document.querySelector('.client-portal'))", 'repeat invite');
  await check('Same invite can reopen after explicit signout', "document.querySelector('.client-hero').textContent.includes('Orbit House')");
  assert.deepEqual(errors, [], 'No uncaught browser errors'); checks.push('No uncaught browser errors');
  writeFileSync(join(out, 'checks.json'), JSON.stringify({ fixture: true, at: new Date().toISOString(), checks, errors, limits: ['No live n8n or connected-provider acceptance', 'Theme checks run separately in qa_themes.mjs'] }, null, 2));
  console.log(`${checks.length} browser checks passed. Evidence: ${out}`);
  try { await send('Browser.close'); } catch { /* Browser may close before response. */ }
} catch (error) { mkdirSync(out, { recursive: true }); writeFileSync(join(out, 'failure.json'), JSON.stringify({ message: error.message, checks, errors }, null, 2)); console.error(error.stack); process.exitCode = 1; }
finally { ws?.close(); if (chrome.exitCode === null) chrome.kill(); }
