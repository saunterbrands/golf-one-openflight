import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestKioskExit } from './kioskService';

describe('requestKioskExit', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses the server cleanup endpoint', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{"status":"shutting_down"}', { status: 200 }));

    await requestKioskExit('0000');

    expect(fetchMock).toHaveBeenCalledWith('/api/shutdown', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ pin: '0000' }),
    });
  });

  it('rejects an unsuccessful response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 503 }));

    await expect(requestKioskExit('0000')).rejects.toThrow('status 503');
  });
});
