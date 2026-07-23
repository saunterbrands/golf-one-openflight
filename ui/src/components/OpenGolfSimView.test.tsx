import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { fuseMetersToYards, OpenGolfSimView } from './OpenGolfSimView';

describe('OpenGolfSimView', () => {
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
});
