import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { requestKioskExit } from '../services/kioskService';
import Logo from '../logo/Logo';
import './KioskExitControl.css';

export const KIOSK_EXIT_TAP_TARGET = 10;
export const KIOSK_EXIT_TAP_WINDOW_MS = 3000;

const KIOSK_EXIT_PIN = '0000';

interface TapSequence {
  count: number;
  startedAt: number | null;
}

interface KioskExitControlProps {
  onExit?: (pin: string) => Promise<void>;
  now?: () => number;
}

/**
 * Hidden kiosk escape hatch. Ten rapid taps in the screen's top-right corner
 * reveal a PIN prompt; the control only becomes visible when keyboard-focused.
 */
export function KioskExitControl({ onExit = requestKioskExit, now = Date.now }: KioskExitControlProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [pin, setPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const tapSequence = useRef<TapSequence>({ count: 0, startedAt: null });
  const hotspotRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const pinInputRef = useRef<HTMLInputElement>(null);

  const closeDialog = useCallback(() => {
    if (isSubmitting) return;

    setIsOpen(false);
    setPin('');
    setError(null);
    hotspotRef.current?.focus();
  }, [isSubmitting]);

  useEffect(() => {
    if (!isOpen) return;

    pinInputRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeDialog();
        return;
      }

      if (event.key === 'Tab') {
        const focusable = Array.from(
          dialogRef.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex="-1"])'
          ) ?? []
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (!first || !last) return;

        if (
          event.shiftKey &&
          (document.activeElement === first || !dialogRef.current?.contains(document.activeElement))
        ) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [closeDialog, isOpen]);

  const handleHotspotTap = () => {
    const timestamp = now();
    const sequence = tapSequence.current;
    const sequenceExpired =
      sequence.startedAt === null ||
      timestamp < sequence.startedAt ||
      timestamp - sequence.startedAt > KIOSK_EXIT_TAP_WINDOW_MS;

    const nextSequence: TapSequence = sequenceExpired
      ? { count: 1, startedAt: timestamp }
      : { count: sequence.count + 1, startedAt: sequence.startedAt };

    if (nextSequence.count >= KIOSK_EXIT_TAP_TARGET) {
      tapSequence.current = { count: 0, startedAt: null };
      setPin('');
      setError(null);
      setIsOpen(true);
      return;
    }

    tapSequence.current = nextSequence;
  };

  const submitPin = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    if (isSubmitting) return;

    if (pin !== KIOSK_EXIT_PIN) {
      setPin('');
      setError('That PIN isn’t correct. Try again.');
      requestAnimationFrame(() => pinInputRef.current?.focus());
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      await onExit(pin);
    } catch {
      setError('Golf One could not open the desktop. Please try again.');
      setIsSubmitting(false);
      requestAnimationFrame(() => pinInputRef.current?.focus());
    }
  };

  return (
    <>
      <button
        ref={hotspotRef}
        type="button"
        className="kiosk-exit-hotspot"
        aria-label="Open kiosk exit"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        tabIndex={isOpen ? -1 : 0}
        onClick={handleHotspotTap}
      >
        <span className="kiosk-exit-hotspot__keyboard-label" aria-hidden="true">
          Exit
        </span>
      </button>

      {isOpen && (
        <div className="kiosk-exit" role="presentation">
          <section
            ref={dialogRef}
            className="kiosk-exit__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="kiosk-exit-title"
            aria-describedby="kiosk-exit-description"
          >
            <button
              type="button"
              className="kiosk-exit__close"
              aria-label="Close kiosk exit"
              onClick={closeDialog}
              disabled={isSubmitting}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.25"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>

            <Logo size="medium" variant="light" />
            <p className="kiosk-exit__eyebrow">System access</p>
            <h2 id="kiosk-exit-title">Exit to desktop</h2>
            <p id="kiosk-exit-description">Enter the four-digit administrator PIN to close Golf One.</p>

            <form className="kiosk-exit__form" onSubmit={submitPin}>
              <label htmlFor="kiosk-exit-pin">Administrator PIN</label>
              <input
                ref={pinInputRef}
                id="kiosk-exit-pin"
                className={`kiosk-exit__pin ${error ? 'kiosk-exit__pin--error' : ''}`}
                type="password"
                inputMode="numeric"
                enterKeyHint="done"
                autoComplete="off"
                maxLength={4}
                value={pin}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? 'kiosk-exit-error' : undefined}
                disabled={isSubmitting}
                onChange={(event) => {
                  setPin(event.target.value.replace(/\D/g, '').slice(0, 4));
                  if (error) setError(null);
                }}
              />

              <div className="kiosk-exit__message" aria-live="polite">
                {error && (
                  <p id="kiosk-exit-error" role="alert">
                    {error}
                  </p>
                )}
              </div>

              <div className="kiosk-exit__actions">
                <button
                  type="button"
                  className="kiosk-exit__button kiosk-exit__button--secondary"
                  onClick={closeDialog}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kiosk-exit__button kiosk-exit__button--primary"
                  disabled={isSubmitting || pin.length !== 4}
                >
                  {isSubmitting ? 'Opening desktop…' : 'Exit Golf One'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
