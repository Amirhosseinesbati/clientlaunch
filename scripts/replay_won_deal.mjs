/** Replay a signed synthetic deal through the local n8n production webhook. */
import { createHmac } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const option = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index < 0 ? fallback : process.argv[index + 1];
};
const url = option('--url', 'http://127.0.0.1:5678/webhook/clientlaunch/won-deal');
const target = new URL(url);
if (target.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(target.hostname)) {
  throw new Error('Fixture replay accepts only a local HTTP target');
}
const caseId = option('--case', 'website-001');
if (!/^[a-zA-Z0-9-]{1,60}$/.test(caseId)) throw new Error('Invalid case suffix');
const env = readFileSync(resolve(root, '.env'), 'utf8');
const secret = env.match(/^WEBHOOK_SECRET=(.+)$/m)?.[1]?.trim();
if (!secret) throw new Error('Run node scripts/demo.mjs first; WEBHOOK_SECRET is missing');
const payload = JSON.parse(readFileSync(resolve(root, 'fixtures/won_deal_website.json'), 'utf8'));
payload.event_id = `cl-demo-${caseId}`;
payload.external_deal_id = `qf-demo-${caseId}`;

const canonical = (value) => JSON.stringify(value, (_key, current) =>
  current && typeof current === 'object' && !Array.isArray(current)
    ? Object.fromEntries(Object.keys(current).sort().map((key) => [key, current[key]]))
    : current);
async function send(label, body) {
  const bytes = canonical(body);
  const signature = createHmac('sha256', secret).update(bytes).digest('hex');
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-ClientLaunch-Signature': `sha256=${signature}` },
    body: bytes, signal: AbortSignal.timeout(15000),
  });
  console.log(`${label}: ${response.status} ${await response.text()}`);
}
await send('initial', payload);
if (process.argv.includes('--repeat')) await send('duplicate', payload);
if (process.argv.includes('--conflict')) {
  await send('conflicting duplicate', { ...payload, approved_scope: `${payload.approved_scope} A conflicting, unapproved change.` });
}
