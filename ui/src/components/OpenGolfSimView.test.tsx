import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { OpenGolfSimView } from './OpenGolfSimView';

describe('OpenGolfSimView', () => {
  it('offers device-owned shot setup and a full-screen simulator launch', () => {
    const html = renderToString(<OpenGolfSimView />);

    expect(html).toContain('Play OpenGolfSim');
    expect(html).toContain('OpenGolfSim account email');
    expect(html).toContain('Connect shots');
    expect(html).toContain('Launch OpenGolfSim');
    expect(html).toContain('The Pi sends one shot');
    expect(html).not.toContain('<iframe');
  });

  it('documents the protected appliance exit gesture', () => {
    const html = renderToString(<OpenGolfSimView />);
    expect(html).toContain('tap the top-right corner 10 times');
    expect(html).toContain('0000');
  });
});
