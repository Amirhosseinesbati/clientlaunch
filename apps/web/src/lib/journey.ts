import type { ChecklistItem, OnboardingSummary } from './api';
import { isCompleteStatus, isAttentionStatus } from './format';

export function nextStep(item: OnboardingSummary): { title: string; description: string } {
  if (item.status === 'paused') return { title: 'On hold', description: 'Review the pause reason before resuming.' };
  if (isAttentionStatus(item.substate ?? undefined)) return { title: 'Resolve the resource issue', description: 'Inspect the recorded outcome in Resources before retrying.' };
  switch (item.status) {
    case 'awaiting_approval': return { title: 'Review the plan', description: 'Approve this revision or request a change.' };
    case 'provisioning': return { title: 'Preparing project resources', description: 'The workflow must confirm folders and the board.' };
    case 'waiting_for_client': return { title: 'Collect client inputs', description: 'Check the invitation and outstanding requests.' };
    case 'ready': return { title: 'Prepare the delivery handoff', description: 'Review intake evidence and record a factual summary.' };
    case 'handed_off': return { title: 'Passed to delivery', description: 'The handoff and its evidence are recorded.' };
    default: return { title: 'Waiting for the draft plan', description: 'A reviewed plan comes before resource provisioning.' };
  }
}

export function clientRequests(items: ChecklistItem[]): ChecklistItem[] {
  return items.filter(item => !isCompleteStatus(item.status)).sort((a, b) => {
    if (a.required !== b.required) return a.required ? -1 : 1;
    return (a.due_at ? new Date(a.due_at).getTime() : Infinity) - (b.due_at ? new Date(b.due_at).getTime() : Infinity);
  });
}

export function inviteCode(raw: string): string {
  const value = raw.trim();
  if (!value) throw new Error('Paste the private code or complete invite link from your project team.');
  if (value.includes('://') || value.startsWith('/')) {
    let url: URL;
    try { url = new URL(value, 'https://clientlaunch.invalid'); } catch { throw new Error('This invite link is incomplete. Ask your project team for the complete link.'); }
    if (!['http:', 'https:'].includes(url.protocol) || url.pathname !== '/client' || !url.searchParams.get('token')) {
      throw new Error('Use a ClientLaunch invite link containing a private access code.');
    }
    return url.searchParams.get('token')!;
  }
  if (/\s/.test(value) || value.length > 512) throw new Error('This code looks incomplete. Copy it again from your welcome message.');
  return value;
}

export function fileProblem(file: Pick<File, 'size' | 'type'>): string | null {
  if (file.size > 5 * 1024 * 1024) return 'This file is larger than 5 MB. Choose a smaller file.';
  if (!['image/png', 'image/jpeg', 'application/pdf'].includes(file.type)) return 'Choose a PNG, JPG or PDF file.';
  if (!file.size) return 'This file is empty. Choose another file.';
  return null;
}

export function brandStyle(accent = '#183e32') {
  const valid = /^#[0-9a-f]{6}$/i.test(accent) ? accent : '#183e32';
  const channels = [1, 3, 5].map(i => parseInt(valid.slice(i, i + 2), 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
  const luminance = channels[0]! * .2126 + channels[1]! * .7152 + channels[2]! * .0722;
  return { '--client-accent': valid, '--client-on-accent': luminance > .179 ? '#172b25' : '#ffffff' };
}
