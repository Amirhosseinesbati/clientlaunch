export function humanize(value?: string | null): string {
  if (!value) return 'Not set';
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatDate(value?: string | null, options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }): string {
  if (!value) return 'Not set';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not set' : new Intl.DateTimeFormat('en', options).format(date);
}

export function compactDate(value?: string | null): string {
  return formatDate(value, { month: 'short', day: 'numeric' });
}

export function initials(name?: string | null): string {
  if (!name) return 'CL';
  return name.trim().split(/\s+/).slice(0, 2).map((word) => word[0]?.toUpperCase() ?? '').join('');
}

export function progress(complete?: number, total?: number, percent?: number): number {
  if (typeof total === 'number' && total > 0 && typeof complete === 'number') {
    return Math.min(100, Math.max(0, Math.round((complete / total) * 100)));
  }
  return Math.min(100, Math.max(0, Math.round(percent ?? 0)));
}

export function isCompleteStatus(status?: string): boolean {
  return ['complete', 'completed', 'done', 'fulfilled', 'approved', 'handed_off', 'succeeded', 'simulated_sent', 'dispatched'].includes((status ?? '').toLowerCase());
}

export function isAttentionStatus(status?: string): boolean {
  return ['failed', 'error', 'uncertain', 'unknown', 'needs_reconciliation', 'blocked', 'recovering'].includes((status ?? '').toLowerCase());
}
