// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://localhost/"}

import { renderToString } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

vi.mock('./state/useUnitPreference', () => ({
  useUnitPreference: () => ({
    unitSystem: 'imperial',
    setUnitSystem: vi.fn(),
  }),
}));

describe('Golf One dashboard routing', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('opens the Live dashboard at the root route', () => {
    const html = renderToString(<App />);

    expect(html).toContain('Ready for your shot');
    expect(html).toContain('nav__button nav__button--active');
    expect(html).not.toContain('Play OpenGolfSim');
    expect(html).not.toContain('<span>Simulator</span>');
  });

  it('opens Settings when explicitly requested', () => {
    window.history.replaceState({}, '', '/?settings=1');

    const html = renderToString(<App />);

    expect(html).toContain('Display Settings');
    expect(html).not.toContain('Ready for your shot');
  });

  it('does not treat the legacy autolaunch query as a simulator route', () => {
    window.history.replaceState({}, '', '/?autolaunch=1');

    const html = renderToString(<App />);

    expect(html).toContain('Ready for your shot');
    expect(html).not.toContain('Play OpenGolfSim');
  });
});
