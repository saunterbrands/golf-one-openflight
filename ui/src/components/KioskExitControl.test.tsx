// @vitest-environment jsdom

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { KIOSK_EXIT_TAP_TARGET, KIOSK_EXIT_TAP_WINDOW_MS, KioskExitControl } from './KioskExitControl';

function click(element: Element) {
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}

function enterPin(input: HTMLInputElement, pin: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  act(() => {
    valueSetter?.call(input, pin);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

describe('KioskExitControl', () => {
  let container: HTMLDivElement;
  let root: Root;
  let timestamp: number;
  let onExit: ReturnType<typeof vi.fn<(pin: string) => Promise<void>>>;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    timestamp = 10_000;
    onExit = vi.fn<(pin: string) => Promise<void>>().mockResolvedValue();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<KioskExitControl onExit={onExit} now={() => timestamp} />);
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  it('keeps an accessible top-right hotspot hidden until ten rapid taps', () => {
    const hotspot = container.querySelector<HTMLButtonElement>('.kiosk-exit-hotspot');

    expect(hotspot).not.toBeNull();
    expect(hotspot?.getAttribute('aria-label')).toBe('Open kiosk exit');
    expect(hotspot?.tagName).toBe('BUTTON');

    for (let tap = 1; tap < KIOSK_EXIT_TAP_TARGET; tap += 1) {
      click(hotspot!);
    }
    expect(container.querySelector('[role="dialog"]')).toBeNull();

    click(hotspot!);
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    expect(document.activeElement?.id).toBe('kiosk-exit-pin');
  });

  it('restarts a tap sequence when the rapid-tap window expires', () => {
    const hotspot = container.querySelector<HTMLButtonElement>('.kiosk-exit-hotspot')!;

    click(hotspot);
    timestamp += KIOSK_EXIT_TAP_WINDOW_MS + 1;
    for (let tap = 1; tap < KIOSK_EXIT_TAP_TARGET; tap += 1) {
      click(hotspot);
    }

    expect(container.querySelector('[role="dialog"]')).toBeNull();
    click(hotspot);
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
  });

  it('rejects an incorrect PIN and exits when 0000 is submitted', async () => {
    const hotspot = container.querySelector<HTMLButtonElement>('.kiosk-exit-hotspot')!;
    for (let tap = 0; tap < KIOSK_EXIT_TAP_TARGET; tap += 1) click(hotspot);

    const input = container.querySelector<HTMLInputElement>('#kiosk-exit-pin')!;
    const form = container.querySelector<HTMLFormElement>('.kiosk-exit__form')!;

    enterPin(input, '1234');
    await act(async () => {
      form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
    });

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('isn’t correct');
    expect(input.value).toBe('');
    expect(onExit).not.toHaveBeenCalled();

    enterPin(input, '0000');
    await act(async () => {
      form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
    });

    expect(onExit).toHaveBeenCalledOnce();
    expect(onExit).toHaveBeenCalledWith('0000');
    expect(container.textContent).toContain('Opening desktop…');
  });

  it('closes the PIN dialog with Escape', () => {
    const hotspot = container.querySelector<HTMLButtonElement>('.kiosk-exit-hotspot')!;
    for (let tap = 0; tap < KIOSK_EXIT_TAP_TARGET; tap += 1) click(hotspot);

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });

    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(hotspot);
  });

  it('shows a recoverable error when the desktop request fails', async () => {
    onExit.mockRejectedValueOnce(new Error('offline'));
    const hotspot = container.querySelector<HTMLButtonElement>('.kiosk-exit-hotspot')!;
    for (let tap = 0; tap < KIOSK_EXIT_TAP_TARGET; tap += 1) click(hotspot);

    const input = container.querySelector<HTMLInputElement>('#kiosk-exit-pin')!;
    enterPin(input, '0000');
    await act(async () => {
      container
        .querySelector<HTMLFormElement>('.kiosk-exit__form')!
        .dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
    });

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('could not open the desktop');
    expect(input.disabled).toBe(false);
  });
});
