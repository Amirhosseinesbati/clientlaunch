/** Isolated headless checks against the local fixture only. Never attaches to a shared browser. */
import { spawn } from 'node:child_process';
import { existsSync, readFileSync, mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import assert from 'node:assert/strict';

const base = 'http://127.0.0.1:4318';
const out = resolve(import.meta.dirname, '../screenshots/theme-2026-10-07');
const profile = mkdtempSync(join(tmpdir(), 'clientlaunch-qa-'));
const checks = [], errors = [], requests = [];
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
    if (data.method === 'Network.requestWillBeSent' && data.params.request.url.includes('/api/') && !data.params.request.url.includes('/health')) requests.push(data.params.request.url);
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

  const appearance = '[aria-label="Appearance"]';
  const overflow = 'document.documentElement.scrollWidth <= innerWidth';
  const mode = () => evaluate("document.documentElement.dataset.theme");
  async function theme(value) { await input(appearance,value); await wait('document.documentElement.dataset.themePreference === '+JSON.stringify(value), 'appearance '+value); }
  await viewport(1440); await navigate('/'); await wait("Boolean(document.querySelector('#email'))",'login');
  await check('Fresh visit starts dark before auth', "document.documentElement.dataset.theme==='dark' && getComputedStyle(document.documentElement).colorScheme==='dark'");
  await shot('auth-dark-desktop'); await theme('light'); await shot('auth-light-desktop');
  await input('#email','fixture@clientlaunch.example.com'); await input('#password','preview'); await click('.auth-submit');
  await wait("Boolean(document.querySelector('.detail-header'))",'workbench detail');
  await check('Fresh workbench exposes queue and details together',"Boolean(document.querySelector('.onboarding-list')) && Boolean(document.querySelector('.detail-header'))");
  await input('[aria-label="Search clients, services, or owners"]','Willow'); await input('#status-filter','active');
  await evaluate("window.qaQueue=document.querySelector('.list-panel');window.qaDetail=document.querySelector('.detail-panel');window.qaLocation=location.href");
  await sleep(300); const before=requests.length; await theme('dark'); await theme('light');
  assert.equal(requests.length,before,'Theme switch must not trigger unrelated business requests'); checks.push('Theme switches cause zero extra business requests');
  await check('Theme preserves queue nodes, filter and current route', "window.qaQueue===document.querySelector('.list-panel') && window.qaDetail===document.querySelector('.detail-panel') && document.querySelector('#status-filter').value==='active' && document.querySelector('[type=search]').value==='Willow' && location.href===window.qaLocation");
  await input('[type=search]',''); await input('#status-filter','all');
  for(const value of ['dark','light']) {
    await theme(value); await shot('workbench-'+value+'-desktop'); await check(value+' desktop workbench fits',overflow);
    await clickText('[role=tab]','Invitation'); await wait("Boolean(document.querySelector('#invite-link'))",'invitation');
    await check(value+' invitation remains honest',"document.body.textContent.includes('Simulated only') && document.body.textContent.includes('does not send an invitation')");
    await shot('invitation-'+value+'-desktop'); await clickText('[role=tab]','Plan');
    const disclosure=await evaluate("document.querySelector('.scope-disclosure').open");
    if(!disclosure) await click('.scope-disclosure summary');
    await check(value+' long scope wraps without clipping',"getComputedStyle(document.querySelector('.readable-detail')).whiteSpace==='pre-wrap' && document.documentElement.scrollWidth<=innerWidth");
    for(const width of [1280,768]) {await viewport(width);await shot('workbench-'+value+'-'+width);await check(value+' workbench '+width+' fits',overflow);}
    await viewport(1440);
  }
  await clickText('.sidebar-nav button','Templates & brand'); await wait("Boolean(document.querySelector('#agency-name'))",'brand');
  await input('#agency-name','Theme proof studio'); await fault('/api/workspace/brand'); await clickText('.settings-card button','Save brand'); await wait("document.body.textContent.includes('Settings not saved')",'brand failure');
  await evaluate("window.qaBrand=document.querySelector('#agency-name');void 0");
  for(const value of ['dark','light']) {
    await theme(value); await check(value+' brand draft and failure survive switching',"window.qaBrand===document.querySelector('#agency-name') && document.querySelector('#agency-name').value==='Theme proof studio' && document.body.textContent.includes('Settings not saved')");
    await shot('brand-'+value+'-desktop');
    await viewport(390); await check(value+' mobile brand fits',overflow); await shot('brand-'+value+'-mobile'); await viewport(1440);
  }
  await clickText('.settings-card button','Save brand'); await wait("document.body.textContent.includes('Brand settings saved')",'brand retry');
  await clickText('.settings-switch button','Service templates'); await wait("Boolean(document.querySelector('#template-name'))",'templates');
  await input('#template-description','A reusable onboarding service with a clear owner and approved deliverables.');
  await evaluate("window.qaTemplate=document.querySelector('#template-description');void 0");
  for(const value of ['dark','light']) {await theme(value);await check(value+' template draft retained',"window.qaTemplate===document.querySelector('#template-description') && document.querySelector('#template-description').value.includes('clear owner')");await shot('templates-'+value+'-desktop');await viewport(390);await check(value+' mobile template fits',overflow);await shot('templates-'+value+'-mobile');await viewport(1440);}
  await clickText('.sidebar-nav button','Onboardings');
  await clickText('.onboarding-row','Willow Harbor'); await wait("document.querySelector('.detail-header')?.textContent.includes('Willow')",'Willow activity');await clickText('[role=tab]','Activity');await click('.welcome-entry summary');
  for(const value of ['dark','light']) {await theme(value);await check(value+' activity and welcome remain readable',overflow);await evaluate("document.querySelector('.detail-tabs').scrollIntoView({block:'start',behavior:'instant'})");await shot('activity-'+value+'-desktop');await viewport(390);await check(value+' mobile activity wraps recorded message',overflow);await shot('activity-'+value+'-mobile');await viewport(1440);}
  await clickText('.onboarding-row','Orbit House');await wait("document.querySelector('.detail-header')?.textContent.includes('Orbit')",'Orbit handoff');await clickText('[role=tab]','Handoff');
  for(const value of ['dark','light']) {await theme(value);await check(value+' handoff evidence stays scoped',"document.body.textContent.includes('Recorded delivery handoff') && document.body.textContent.includes('Fixture handoff')");await evaluate("document.querySelector('.detail-tabs').scrollIntoView({block:'start',behavior:'instant'})");await shot('handoff-'+value+'-desktop');}
  await evaluate("window.scrollTo({top:0,behavior:'instant'})");
  await clickText('.onboarding-row','Atlas Fieldwork'); await wait("document.querySelector('.detail-header')?.textContent.includes('Atlas')",'Atlas');
  await clickText('[role=tab]','Resources'); await wait("document.body.textContent.includes('Fixture board service')",'recovery ledger');
  for(const value of ['dark','light']) {await theme(value);await shot('recovery-'+value+'-desktop');await check(value+' recovery separates existing and failed resources',"document.body.textContent.includes('fixture-folder-atlas') && document.body.textContent.includes('Existing folder is retained')");await evaluate("document.querySelector('.detail-tabs').scrollIntoView({block:'start',behavior:'instant'})");await shot('recovery-'+value+'-ledger');await evaluate("window.scrollTo({top:0,behavior:'instant'})");}
  await clickText('.recovery-controls button','Continue');await wait("document.body.textContent.includes('Recovery request recorded')",'recovery');
  await check('Recovery queues only missing operation and retains folder',"document.body.textContent.includes('fixture-folder-atlas') && document.body.textContent.includes('Pending') && document.body.textContent.includes('No n8n')");
  await viewport(390); await sleep(150);
  if (await evaluate("Boolean(document.querySelector('[role=dialog]'))")) { await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27}); await wait("!document.querySelector('.detail-open')",'close details before navigation'); }
  await click('.mobile-menu-button'); await wait("document.querySelector('.sidebar-open')?.contains(document.activeElement)",'menu focus');
  await evaluate("window.qaMenu=document.querySelector('.sidebar-open');window.clientlaunchTheme.set('dark')");
  await check('Theme switching keeps mobile menu and focus',"window.qaMenu===document.querySelector('.sidebar-open') && document.querySelector('.sidebar-open').contains(document.activeElement)");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,modifiers:8});
  await check('Mobile navigation wraps reverse keyboard focus',"document.querySelector('.sidebar-open').contains(document.activeElement)");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await wait("!document.querySelector('.sidebar-open')",'menu closed');
  await check('Menu Escape returns focus to its trigger',"!document.querySelector('.sidebar-open') && document.activeElement.classList.contains('mobile-menu-button')");
  await clickText('.onboarding-row','Willow Harbor');await wait("Boolean(document.querySelector('[role=dialog]'))",'mobile details');
  await evaluate("window.qaDialog=document.querySelector('[role=dialog]');window.clientlaunchTheme.set('light')");
  await check('Theme switching preserves mobile detail dialog and focus',"window.qaDialog===document.querySelector('[role=dialog]') && document.querySelector('[role=dialog]').contains(document.activeElement)");
  await shot('detail-light-mobile');await evaluate("window.clientlaunchTheme.set('dark')");await shot('detail-dark-mobile');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await wait("!document.querySelector('.detail-open')",'detail close');await shot('queue-dark-mobile');await theme('light');await shot('queue-light-mobile');
  await viewport(1440);await navigate('/client');await wait("Boolean(document.querySelector('#portal-token'))",'client entry');
  await input('#portal-token','expired-synthetic-link');await clickText('button','Open my project');await wait("Boolean(document.querySelector('.error-state'))",'invalid link');
  for(const value of ['dark','light']) {await theme(value);await shot('access-error-'+value+'-desktop');await check(value+' invitation error keeps input',"document.querySelector('#portal-token').value==='expired-synthetic-link' && Boolean(document.querySelector('.error-state'))");}
  await input('#portal-token','fixture-willow');await clickText('button','Open my project');await wait("Boolean(document.querySelector('.client-portal'))",'client workspace');
  await clickText('button','Start this request');await wait("document.activeElement.id==='answer-text'",'answer focus');await input('#answer-text','Theme-safe browser draft. Approved content will arrive tomorrow.');
  await fault('/api/client/submissions');await clickText('button','Send answer');await wait("document.body.textContent.includes('Answer not sent')",'answer failure');
  await evaluate("window.qaAnswer=document.querySelector('#answer-text');window.qaProject=location.href");
  for(const value of ['dark','light']) {
    const count=requests.length;await theme(value);assert.equal(requests.length,count,'Client theme switch must not refetch project');checks.push(value+' client theme creates no extra requests');
    await check(value+' answer draft and failure are retained',"window.qaAnswer===document.querySelector('#answer-text') && document.querySelector('#answer-text').value.includes('Theme-safe') && document.body.textContent.includes('Answer not sent') && location.href===window.qaProject");
    await evaluate('window.scrollTo(0,0)');await shot('client-'+value+'-desktop');
    await evaluate("document.querySelector('#answer-text').scrollIntoView({block:'center',behavior:'instant'})");await shot('submission-error-'+value+'-desktop');
    await viewport(390);await evaluate('window.scrollTo(0,0)');await shot('client-'+value+'-mobile');await check(value+' mobile client fits',overflow);
    await evaluate("document.querySelector('#answer-text').scrollIntoView({block:'center',behavior:'instant'})");await shot('submission-error-'+value+'-mobile');await viewport(1440);
  }
  await clickText('button','Send answer');await wait("document.body.textContent.includes('Answer received')",'answer retry');await check('Retry succeeds and creates a visible receipt',"document.querySelector('#answer-text').value==='' && document.querySelector('.client-received-inputs').textContent.includes('Theme-safe')");
  await theme('light');await navigate('/client');await wait("Boolean(document.querySelector('.client-portal'))",'theme persistence');
  await check('Persisted Light survives full navigation',"document.documentElement.dataset.theme==='light' && document.querySelector('[aria-label=Appearance]').value==='light'");
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'dark'}]});await theme('system');await wait("document.documentElement.dataset.theme==='dark'",'System dark');
  await check('System responds to dark OS preference',"document.documentElement.dataset.theme==='dark' && document.querySelector('[aria-label=Appearance]').value==='system'");
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'light'}]});await wait("document.documentElement.dataset.theme==='light'",'System light');
  await check('System follows a changing OS preference',"document.documentElement.dataset.theme==='light'");
  await theme('dark');await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'light'}]});await sleep(100);await check('Explicit Dark ignores OS changes',"document.documentElement.dataset.theme==='dark'");
  await theme('light');await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'dark'}]});await check('Explicit Light ignores OS changes',"document.documentElement.dataset.theme==='light'");
  await navigate('/api/fixture/theme-probe');await wait("Boolean(window.clientlaunchTheme) && Boolean(document.body)",'CSP probe');
  await check('Pre-paint initializer executes under script-src self CSP',"document.documentElement.dataset.theme==='light' && getComputedStyle(document.body).backgroundColor==='rgb(244, 247, 250)' && ![...document.scripts].some(s=>!s.src)");
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"Object.defineProperty(Storage.prototype,'getItem',{value:function(){throw new Error('synthetic storage restriction')}});Object.defineProperty(Storage.prototype,'setItem',{value:function(){throw new Error('synthetic storage restriction')}});"});
  await navigate('/client?token=fixture-willow');await wait("Boolean(document.querySelector('.client-portal'))",'blocked storage client');
  await check('Blocked storage safely falls back to Dark',"document.documentElement.dataset.theme==='dark'");
  await theme('light');await clickText('button','Start this request');await input('#answer-text','Memory-only draft retained despite unavailable storage.');await theme('dark');
  await check('Theme and memory draft work with blocked storage',"document.documentElement.dataset.theme==='dark' && document.querySelector('#answer-text').value.includes('Memory-only')");
  await viewport(390);await theme('light');await check('Blocked storage mobile Light fits',overflow);
  assert.deepEqual(errors,[],'No uncaught browser exceptions');checks.push('No uncaught browser exceptions');
  writeFileSync(join(out,'theme-checks.json'),JSON.stringify({at:new Date().toISOString(),fixture:true,checks,errors,businessRequestCount:requests.length,limits:['No live n8n, AI, mail or provider acceptance','Fixture recovery queues work; it does not execute external steps']},null,2));
  console.log(checks.length+' theme/browser checks passed. Evidence: '+out);
  try {await send('Browser.close');}catch{/* Browser closes before response. */}
} catch(error) {mkdirSync(out,{recursive:true});writeFileSync(join(out,'theme-failure.json'),JSON.stringify({message:error.message,checks,errors},null,2));console.error(error.stack);process.exitCode=1;}
finally {ws?.close();if(chrome.exitCode===null)chrome.kill();}
