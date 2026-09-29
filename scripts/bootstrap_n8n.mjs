import { readFileSync, writeFileSync, mkdirSync, existsSync, unlinkSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const root = resolve(import.meta.dirname, '..');
const runtime = resolve(root, '.runtime');
mkdirSync(runtime, { recursive: true });
const manifest = JSON.parse(readFileSync(resolve(root, 'workflows/manifest.json'), 'utf8'));
const environment = Object.fromEntries(readFileSync(resolve(root, '.env'), 'utf8').split(/\r?\n/)
  .filter((line) => line && !line.startsWith('#')).map((line) => {
    const index = line.indexOf('=');
    return [line.slice(0, index), line.slice(index + 1)];
  }));
const force = process.argv.includes('--force');
const publishDemo = process.argv.includes('--publish-demo');
const enableDemoSchedule = process.argv.includes('--enable-demo-schedule');
if (enableDemoSchedule && !publishDemo) throw new Error('--enable-demo-schedule requires --publish-demo');
if (enableDemoSchedule && environment.CONNECTOR_MODE !== 'demo') {
  throw new Error('The demo reminder schedule can only be published with CONNECTOR_MODE=demo');
}
const hash = (value) => createHash('sha256').update(value).digest('hex');

function docker(...args) {
  const result = spawnSync('docker', ['compose', ...args], { cwd: root, stdio: 'inherit' });
  if (result.status !== 0) throw new Error(`docker compose ${args[0]} failed with exit code ${result.status}`);
}

function dockerOutput(...args) {
  const result = spawnSync('docker', ['compose', ...args], { cwd: root, encoding: 'utf8' });
  if (result.status !== 0) throw new Error(`docker compose ${args[0]} failed: ${result.stderr}`);
  return result.stdout;
}

async function waitForN8n() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch('http://127.0.0.1:5678/healthz', { signal: AbortSignal.timeout(1500) });
      if (response.ok) return;
    } catch { /* The process is restarting. */ }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error('n8n did not become healthy after restart');
}

const credentialMarker = resolve(runtime, 'credential-imported');
const credentialHash = hash(environment.INTERNAL_KEY ?? '');
if (force || !existsSync(credentialMarker) || readFileSync(credentialMarker, 'utf8') !== credentialHash) {
  const credentialPath = resolve(runtime, 'clientlaunch-internal-credential.json');
  const credential = [{
    id: 'CL08InternalAuth', name: 'ClientLaunch internal API', type: 'httpHeaderAuth',
    data: { name: 'X-Internal-Key', value: environment.INTERNAL_KEY }, isManaged: false,
  }];
  if (!environment.INTERNAL_KEY) throw new Error('INTERNAL_KEY is missing from .env');
  try {
    writeFileSync(credentialPath, JSON.stringify(credential), { mode: 0o600 });
    docker('exec', '-T', 'n8n', 'n8n', 'import:credentials', '--input=/bootstrap/clientlaunch-internal-credential.json');
    writeFileSync(credentialMarker, credentialHash);
  } finally {
    if (existsSync(credentialPath)) unlinkSync(credentialPath);
  }
}

const changed = new Set();
for (const key of manifest.import_order) {
  const entry = manifest.workflows.find((workflow) => workflow.id && workflow.file === `${key}.json`);
  if (!entry) throw new Error(`Manifest has no workflow for ${key}`);
  const marker = resolve(runtime, `imported-${key}`);
  const source = readFileSync(resolve(root, 'workflows', entry.file), 'utf8');
  const sourceHash = hash(source);
  if (force || !existsSync(marker) || readFileSync(marker, 'utf8') !== sourceHash) {
    const workflow = JSON.parse(source);
    if (workflow.id !== entry.id) throw new Error(`Workflow ID mismatch for ${key}`);
    docker('exec', '-T', 'n8n', 'n8n', 'import:workflow', `--input=/workflows/${entry.file}`);
    writeFileSync(marker, sourceHash);
    changed.add(key);
  }
}

// CLI imports preserve supplied IDs. Verify the installed objects before
// publishing so a failed import cannot leave broken cross-workflow references.
const exportPath = resolve(runtime, 'import-verification.json');
try {
  docker('exec', '-T', 'n8n', 'n8n', 'export:workflow', '--all', '--output=/tmp/clientlaunch-import-verification.json');
  docker('cp', 'n8n:/tmp/clientlaunch-import-verification.json', exportPath);
  const installed = JSON.parse(readFileSync(exportPath, 'utf8'));
  const list = Array.isArray(installed) ? installed : [installed];
  for (const entry of manifest.workflows) {
    const imported = list.find((workflow) => workflow.id === entry.id && workflow.name === JSON.parse(readFileSync(resolve(root, 'workflows', entry.file), 'utf8')).name);
    if (!imported) throw new Error(`Imported workflow ID/name could not be resolved: ${entry.file}`);
  }
} finally {
  if (existsSync(exportPath)) unlinkSync(exportPath);
}

const demoPublished = publishDemo ? ['drive', 'trello', 'error', 'task_sync', 'intake', 'provision', 'submission', 'recovery'] : [];
if (enableDemoSchedule) demoPublished.push('reminder', 'dispatch_sweeper');
for (const key of demoPublished) {
  const marker = resolve(runtime, `published-${key}`);
  if (force || changed.has(key) || !existsSync(marker)) {
    docker('exec', '-T', 'n8n', 'n8n', 'publish:workflow', `--id=${manifest.workflows.find((workflow) => workflow.file === `${key}.json`).id}`);
    writeFileSync(marker, new Date().toISOString());
  }
}
docker('restart', 'n8n');
if (publishDemo) {
  const expected = new Map();
  for (const entry of manifest.workflows) {
    const workflow = JSON.parse(readFileSync(resolve(root, 'workflows', entry.file), 'utf8'));
    for (const node of workflow.nodes) {
      if (node.type === 'n8n-nodes-base.webhook') expected.set(node.parameters.path, entry.id);
    }
  }
  const missingWebhooks = () => {
    const rows = dockerOutput('exec', '-T', 'db', 'psql', '-U', 'clientlaunch', '-d', 'n8n', '-At', '-c',
      'SELECT "webhookPath" FROM webhook_entity').trim().split(/\r?\n/);
    return [...expected].filter(([path]) => !rows.includes(path));
  };
  const waitForRegistrations = async () => {
    let missing = [];
    for (let attempt = 0; attempt < 10; attempt += 1) {
      missing = missingWebhooks();
      if (!missing.length) return missing;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    return missing;
  };
  await waitForN8n();
  let missing = await waitForRegistrations();
  if (missing.length) {
    console.warn(`Retrying registration of ${missing.length} missing demo webhook(s).`);
    for (const [, id] of missing) docker('exec', '-T', 'n8n', 'n8n', 'publish:workflow', `--id=${id}`);
    docker('restart', 'n8n');
    await waitForN8n();
    missing = await waitForRegistrations();
  }
  if (missing.length) throw new Error(`Demo webhooks were not registered: ${missing.map(([path]) => path).join(', ')}`);
}
console.log(`ClientLaunch workflow pack imported and IDs checked. ${publishDemo ? 'Demo webhooks, connector subflows, and the shared error workflow were published.' : 'Imported workflows remain unpublished.'} Reminder and dispatch schedules ${enableDemoSchedule ? 'published for DEMO' : 'remain unpublished'}.`);
