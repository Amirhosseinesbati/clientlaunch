import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('browser API boundary', () => {
  it('binds approval to the exact plan and sends the operator CSRF token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'approved' }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);

    await api.decidePlan('onboarding-1', 'csrf-123', 'revision-4', 'proposal-hash', 'approve');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/onboardings/onboarding-1/approval');
    expect(init.credentials).toBe('include');
    expect(init.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-123', 'Content-Type': 'application/json' });
    expect(JSON.parse(String(init.body))).toEqual({ plan_revision_id: 'revision-4', proposal_hash: 'proposal-hash', decision: 'approve' });
  });

  it('sends the scoped client session in a bearer header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ onboarding: {}, checklist: [], assets: [], submissions: [], next_actions: [] }), { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);

    await api.clientOnboarding('scoped-client-token');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/client/onboarding');
    expect(init.headers).toMatchObject({ Authorization: 'Bearer scoped-client-token' });
  });

  it('shows the API rejection instead of treating it as success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Outcome remains uncertain' }), { status: 409, headers: { 'content-type': 'application/json' } })));
    await expect(api.recover('onboarding-1', 'csrf', 'operation-1', 'retry')).rejects.toEqual(new ApiError('Outcome remains uncertain', 409));
  });
});
