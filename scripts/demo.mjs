import { randomBytes } from 'node:crypto';
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = resolve(import.meta.dirname, '..');
const envFile = resolve(root, '.env');
const runtime = resolve(root, '.runtime');
mkdirSync(runtime, { recursive: true });
const random = () => randomBytes(24).toString('hex');
let firstRun = false;
if (!existsSync(envFile)) {
  const template = readFileSync(resolve(root, '.env.example'), 'utf8');
  const replacements = {
    DB_PASSWORD: random(), INTERNAL_KEY: random(), WEBHOOK_SECRET: random(),
    SESSION_SECRET: random(), N8N_ENCRYPTION_KEY: random(), DEMO_ADMIN_PASSWORD: random(),
    N8N_OWNER_PASSWORD: `A1${random()}`,
  };
  const body = template.replace(/^(DB_PASSWORD|INTERNAL_KEY|WEBHOOK_SECRET|SESSION_SECRET|N8N_ENCRYPTION_KEY|N8N_OWNER_PASSWORD|DEMO_ADMIN_PASSWORD)=REPLACE_WITH_RANDOM$/gm,
    (_, key) => `${key}=${replacements[key]}`);
  writeFileSync(envFile, body, { flag: 'wx', mode: 0o600 });
  firstRun = true;
}
const configuredMode = readFileSync(envFile, 'utf8').match(/^CONNECTOR_MODE=(.*)$/m)?.[1]?.trim() || 'demo';
if (configuredMode !== 'demo') {
  throw new Error('scripts/demo.mjs requires CONNECTOR_MODE=demo; import connected workflows without publishing, then configure authorized accounts explicitly');
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: root, stdio: 'inherit',
    env: { ...process.env, COMPOSE_PARALLEL_LIMIT: '1' },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} ${args[0]} failed with exit code ${result.status}`);
}

run('docker', ['compose', 'up', '-d', 'db']);
for (const service of ['api', 'ai', 'web']) {
  run('docker', ['compose', 'build', service]);
}
run('docker', ['compose', 'run', '--rm', '--no-deps', 'api', 'alembic', '-c', 'apps/api/alembic.ini', 'upgrade', 'head']);
run('docker', ['compose', 'up', '-d']);
let ready = false;
for (let attempt = 0; attempt < 60; attempt += 1) {
  try {
    const response = await fetch('http://localhost:5678/healthz', { signal: AbortSignal.timeout(1500) });
    if (response.ok) { ready = true; break; }
  } catch { /* n8n is still starting */ }
  await new Promise((done) => setTimeout(done, 2000));
}
if (!ready) throw new Error('n8n did not become healthy within 120 seconds; inspect docker compose logs n8n');
let n8nSettings;
for (let attempt = 0; attempt < 20; attempt += 1) {
  try {
    const response = await fetch('http://127.0.0.1:5678/rest/settings', { signal: AbortSignal.timeout(5000) });
    if (response.ok) { n8nSettings = await response.json(); break; }
  } catch { /* The settings route can lag behind healthz during startup. */ }
  await new Promise((done) => setTimeout(done, 1000));
}
if (!n8nSettings) throw new Error('Could not read local n8n setup state after startup');
if (n8nSettings.data?.userManagement?.showSetupOnFirstLoad) {
  let ownerPassword = readFileSync(envFile, 'utf8').match(/^N8N_OWNER_PASSWORD=(.*)$/m)?.[1];
  if (!ownerPassword) {
    ownerPassword = `A1${random()}`;
    appendFileSync(envFile, `\nN8N_OWNER_PASSWORD=${ownerPassword}\n`);
  }
  const ownerResponse = await fetch('http://127.0.0.1:5678/rest/owner/setup', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'n8n-demo@clientlaunch.example.com', firstName: 'Demo', lastName: 'Owner', password: ownerPassword }),
    signal: AbortSignal.timeout(10000),
  });
  if (!ownerResponse.ok) throw new Error(`Local n8n owner setup failed with HTTP ${ownerResponse.status}`);
  console.log('Local n8n demo owner configured; its password is stored only in the ignored .env file.');
}
run('docker', ['compose', 'exec', '-T', 'api', 'python', '-m', 'scripts.seed', '--mode', 'full']);
run(process.execPath, [resolve(root, 'scripts/bootstrap_n8n.mjs'), '--publish-demo', '--enable-demo-schedule']);
console.log('Portal: http://localhost:8080 | API: http://localhost:8018 | n8n: http://localhost:5678');
console.log('Demo operator: operator@northstar.example.com');
console.log('n8n demo owner: n8n-demo@clientlaunch.example.com');
if (firstRun) {
  const password = readFileSync(envFile, 'utf8').match(/^DEMO_ADMIN_PASSWORD=(.*)$/m)?.[1];
  console.log(`Generated local demo password: ${password}`);
} else {
  console.log('Local demo password is stored only in the ignored .env file.');
}
