import { afterEach, expect, it, vi } from 'vitest';
import { api, ApiError } from './api';
afterEach(() => vi.unstubAllGlobals());

it('describes an unconfirmed write as uncertain rather than definitely unsaved', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network lost')));
  await expect(api.clientSubmit('scoped', [{ checklist_item_id: 'request', value: 'answer' }])).rejects.toMatchObject({ status: 0, message: expect.stringContaining('before the result was confirmed') });
});

it('keeps unreachable reads distinct and limits the request lifetime', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new TypeError('Network lost'));
  vi.stubGlobal('fetch', fetchMock);
  await expect(api.health()).rejects.toEqual(new ApiError('Cannot reach ClientLaunch. Check that the API is running and try again.', 0));
  expect(fetchMock.mock.calls[0]?.[1]?.signal).toBeInstanceOf(AbortSignal);
});
