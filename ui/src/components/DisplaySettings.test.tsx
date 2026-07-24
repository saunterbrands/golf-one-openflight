// @vitest-environment jsdom

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplaySettings } from './DisplaySettings';

describe('DisplaySettings', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('offers manual display choices while keeping the Dashboard as startup', () => {
    const html = renderToString(<DisplaySettings />);

    expect(html).toContain('Display Settings');
    expect(html).toContain('Optimized Local Practice Range');
    expect(html).toContain('OpenGolfSim Online');
    expect(html).toContain('Wide Launch Monitor');
    expect(html).toContain('DEVICE-OPTIMIZED');
    expect(html).toContain('Golf One Dashboard always starts first');
    expect(html).toContain('Remembered');
    expect(html).toContain('Show selected display');
    expect(html).not.toContain('Default display');
  });

  it('loads and persists the optimized local simulator selection on the Pi', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (String(_input).endsWith('/api/opengolfsim/runtime')) {
        return new Response(
          JSON.stringify({
            offline_available: true,
            offline_profile: 'pi-balanced',
            build_variant: 'range-explicit-webgl-anisotropy4-v3',
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }
      const payload =
        init?.method === 'POST'
          ? { mode: 'practice_range', url: '/offline-simulator' }
          : { mode: 'simulator', url: 'https://app.opengolfsim.com/account/simulator' };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await act(async () => {
      root.render(<DisplaySettings />);
    });

    const localRangeOption = [...container.querySelectorAll<HTMLButtonElement>('[role="radio"]')].find((button) =>
      button.textContent?.includes('Optimized Local Practice Range')
    );
    expect(localRangeOption).toBeDefined();
    act(() => localRangeOption?.click());

    const saveButton = [...container.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === 'Remember selection'
    );
    await act(async () => {
      saveButton?.click();
    });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const saveCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(String(saveCall?.[0])).toMatch(/\/api\/display-mode$/);
    expect(saveCall?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ mode: 'practice_range' }),
    });
    expect(container.textContent).toContain(
      'Optimized Local Practice Range is now remembered on this Golf One. The Dashboard will still open first.'
    );
    expect(container.textContent).toContain('Pi 5 balanced profile installed');
  });
});
