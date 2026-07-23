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

  it('offers the simulator and wide launch-monitor display modes', () => {
    const html = renderToString(<DisplaySettings />);

    expect(html).toContain('Display Settings');
    expect(html).toContain('OpenGolfSim Simulator');
    expect(html).toContain('Wide Launch Monitor');
    expect(html).toContain('Default display');
    expect(html).toContain('Show selected display');
  });

  it('loads and persists the selected default display on the Pi', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const payload =
        init?.method === 'POST'
          ? { mode: 'launch_monitor', url: '/display' }
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

    const wideOption = [...container.querySelectorAll<HTMLButtonElement>('[role="radio"]')].find((button) =>
      button.textContent?.includes('Wide Launch Monitor')
    );
    expect(wideOption).toBeDefined();
    act(() => wideOption?.click());

    const saveButton = [...container.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === 'Save as default'
    );
    await act(async () => {
      saveButton?.click();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toMatch(/\/api\/display-mode$/);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ mode: 'launch_monitor' }),
    });
    expect(container.textContent).toContain('Wide Launch Monitor is now the default display.');
  });
});
