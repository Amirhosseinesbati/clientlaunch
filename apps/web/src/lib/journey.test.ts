import { describe, expect, it } from 'vitest';
import type { ChecklistItem, OnboardingSummary } from './api';
import { brandStyle, clientRequests, fileProblem, inviteCode, nextStep } from './journey';

describe('onboarding decisions', () => {
  const summary = { status: 'waiting_for_client', client_name: 'Harbor', service_names: [] } as unknown as OnboardingSummary;
  it('prioritizes uncertain resources over asking the client for inputs', () => {
    expect(nextStep({ ...summary, substate: 'uncertain' }).title).toBe('Resolve the resource issue');
    expect(nextStep({ ...summary, status: 'paused' }).title).toBe('On hold');
    expect(nextStep({ ...summary, status: 'ready' }).title).toBe('Prepare the delivery handoff');
  });
  it('prioritizes required requests and removes completed ones', () => {
    const items = [{ id: 'optional', required: false, status: 'pending' }, { id: 'required', required: true, status: 'pending' }, { id: 'done', required: true, status: 'completed' }] as ChecklistItem[];
    expect(clientRequests(items).map(i => i.id)).toEqual(['required', 'optional']);
  });
  it('accepts a full invite link, relative invite and bare code without visiting it', () => {
    expect(inviteCode(' https://agency.example/client?token=private%2Bcode ')).toBe('private+code');
    expect(inviteCode('/client?token=abc')).toBe('abc');
    expect(inviteCode(' code ')).toBe('code');
    expect(() => inviteCode('https://example.com/other?token=abc')).toThrow();
    expect(() => inviteCode('two words')).toThrow();
    expect(() => inviteCode('https://example.com/client')).toThrow();
  });
  it('rejects unsupported, empty and oversized files before upload', () => {
    expect(fileProblem({ size: 1, type: 'image/png' })).toBeNull();
    expect(fileProblem({ size: 6 * 1024 * 1024, type: 'application/pdf' })).toContain('5 MB');
    expect(fileProblem({ size: 1, type: 'text/plain' })).toContain('PNG');
    expect(fileProblem({ size: 0, type: 'image/png' })).toContain('empty');
  });
  it('keeps readable text on very light and dark brand accents', () => {
    expect(brandStyle('#ffffff')['--client-on-accent']).toBe('#172b25');
    expect(brandStyle('#000000')['--client-on-accent']).toBe('#ffffff');
    expect(brandStyle('bad')['--client-accent']).toBe('#183e32');
  });
});
