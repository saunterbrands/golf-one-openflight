// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://localhost/"}

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fuseMetersToYards, OpenGolfSimView } from './OpenGolfSimView';

describe('OpenGolfSimView', () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    window.history.replaceState({}, '', '/');
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('offers device-owned shot setup and a full-screen simulator launch', () => {
    const html = renderToString(<OpenGolfSimView />);

    expect(html).toContain('Play OpenGolfSim');
    expect(html).toContain('Optional compatibility relay email');
    expect(html).toContain('Save fallback');
    expect(html).toContain('Open OpenGolfSim Online');
    expect(html).toContain('Offline Practice Range');
    expect(html).toContain('The Pi sends one shot');
    expect(html).toContain('Shots connect automatically when you open a course');
    expect(html).toContain('A normal sign-in stays in this Pi');
    expect(html).not.toContain('<iframe');
  });

  it('documents the protected appliance exit gesture', () => {
    const html = renderToString(<OpenGolfSimView />);
    expect(html).toContain('tap the top-right corner 10 times');
    expect(html).toContain('0000');
  });

  it('converts the FUSE metre result before labeling carry as yards', () => {
    expect(fuseMetersToYards(191.32)).toBeCloseTo(209.23, 2);
  });

  it('never auto-redirects when the legacy autolaunch query is present', async () => {
    window.history.replaceState({}, '', '/?autolaunch=1');
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      void input;
      return new Response(
        JSON.stringify({
          configured: false,
          email: '',
          state: 'disabled',
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    });
    vi.stubGlobal('fetch', fetchMock);
    const root = createRoot(container);

    await act(async () => {
      root.render(<OpenGolfSimView />);
    });

    expect(fetchMock).toHaveBeenCalled();
    expect(fetchMock.mock.calls.map(([input]) => String(input))).not.toEqual(
      expect.arrayContaining([expect.stringMatching(/\/api\/display-mode$/)])
    );

    act(() => root.unmount());
  });
});
