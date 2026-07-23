import { useEffect, useState, type FormEvent } from 'react';
import { getServerOrigin } from '../utils/serverOrigin';
import './OpenGolfSimView.css';

const OPEN_GOLF_SIM_WEB_URL = 'https://app.opengolfsim.com/account/simulator';
const DISPLAY_MODE_API_URL = `${getServerOrigin()}/api/display-mode`;
const OPEN_GOLF_SIM_API_URL = `${getServerOrigin()}/api/opengolfsim`;

type BridgeState = 'disabled' | 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';

interface OpenGolfSimStatus {
  configured: boolean;
  email: string;
  state: BridgeState;
  message?: string;
  browser?: {
    active: boolean;
    game_state: 'inactive' | 'loading' | 'ready' | 'queued' | 'in_flight';
    last_delivery?: {
      state: 'queued' | 'posted' | 'completed' | 'error';
      result?: { carry?: number; total?: number };
    } | null;
  };
}

const EMPTY_STATUS: OpenGolfSimStatus = {
  configured: false,
  email: '',
  state: 'disabled',
};

const statusCopy = (status: OpenGolfSimStatus) => {
  if (status.browser?.active && status.browser.game_state === 'ready') {
    const carry = status.browser.last_delivery?.result?.carry;
    return typeof carry === 'number' ? `Game ready — last carry ${Math.round(carry)} yd` : 'OpenGolfSim game ready';
  }
  if (status.browser?.active && (status.browser.game_state === 'queued' || status.browser.game_state === 'in_flight')) {
    return 'Shot is playing in OpenGolfSim';
  }
  if (status.browser?.active) return 'OpenGolfSim course is loading';
  if (status.state === 'connected') return 'Shot bridge connected';
  if (status.state === 'connecting') return 'Connecting shot bridge';
  if (status.state === 'reconnecting') return 'Reconnecting shot bridge';
  if (status.state === 'error') return status.message || 'OpenGolfSim needs attention';
  if (status.configured) return status.message || 'Compatibility relay offline';
  return 'Shots connect automatically when you open a course';
};

export function OpenGolfSimView() {
  const [status, setStatus] = useState<OpenGolfSimStatus>(EMPTY_STATUS);
  const [email, setEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(() =>
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('autolaunch') === '1'
      ? 'Opening your default display…'
      : ''
  );

  useEffect(() => {
    const shouldAutoLaunch =
      new URLSearchParams(window.location.search).get('autolaunch') === '1' &&
      window.sessionStorage.getItem('golf-one:opengolfsim-autolaunched') !== '1';
    if (!shouldAutoLaunch) return;

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);

    const launchDefaultDisplay = async () => {
      try {
        const preferenceResponse = await fetch(DISPLAY_MODE_API_URL, {
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        });
        if (preferenceResponse.ok) {
          const preference = (await preferenceResponse.json()) as { mode?: string };
          if (preference.mode === 'launch_monitor') {
            window.location.assign('/display');
            return;
          }
        }

        await fetch(OPEN_GOLF_SIM_WEB_URL, {
          mode: 'no-cors',
          signal: controller.signal,
        });
        window.sessionStorage.setItem('golf-one:opengolfsim-autolaunched', '1');
        window.location.assign(OPEN_GOLF_SIM_WEB_URL);
      } catch {
        setFeedback('The default display could not open. Check Wi-Fi or choose another display in Settings.');
      } finally {
        window.clearTimeout(timeout);
      }
    };

    void launchDefaultDisplay();

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, []);

  useEffect(() => {
    let active = true;

    const refresh = async () => {
      try {
        const response = await fetch(OPEN_GOLF_SIM_API_URL, { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error(`status ${response.status}`);
        const nextStatus = (await response.json()) as OpenGolfSimStatus;
        if (!active) return;
        setStatus(nextStatus);
        setEmail((current) => current || nextStatus.email || '');
      } catch {
        if (active) {
          setStatus({
            configured: false,
            email: '',
            state: 'error',
            message: 'Golf One could not read the shot-bridge status',
          });
        }
      }
    };

    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const saveAccount = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedEmail = email.trim();
    if (!normalizedEmail) return;

    setSaving(true);
    setFeedback('Saving account…');
    try {
      const response = await fetch(OPEN_GOLF_SIM_API_URL, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: normalizedEmail }),
      });
      const result = (await response.json()) as OpenGolfSimStatus & { error?: string };
      if (!response.ok) throw new Error(result.error || `status ${response.status}`);
      setStatus(result);
      setEmail(result.email || normalizedEmail);
      setFeedback('Saved. Golf One is connecting the shot bridge.');
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Could not save the OpenGolfSim account.');
    } finally {
      setSaving(false);
    }
  };

  const launchSimulator = () => {
    window.location.assign(OPEN_GOLF_SIM_WEB_URL);
  };

  return (
    <section className="ogs-view" aria-label="OpenGolfSim simulator">
      <div className="ogs-view__hero">
        <div className="ogs-view__brand-row">
          <span className="ogs-view__mark" aria-hidden="true">
            G1
          </span>
          <div>
            <span className="ogs-view__eyebrow">GOLF ONE SIMULATOR</span>
            <h1>Play OpenGolfSim</h1>
          </div>
        </div>

        <p className="ogs-view__intro">
          OpenGolfSim runs full-screen in this kiosk. When a course opens, Golf One connects it directly to the launch
          monitor on this Pi—no separate device pairing is required.
        </p>

        <form className="ogs-view__connect" onSubmit={saveAccount}>
          <label htmlFor="ogs-account-email">Optional compatibility relay email</label>
          <div className="ogs-view__input-row">
            <input
              id="ogs-account-email"
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <button type="submit" disabled={saving || !email.trim()}>
              {saving ? 'Saving…' : status.configured ? 'Update relay' : 'Save fallback'}
            </button>
          </div>
        </form>

        <div
          className={`ogs-view__status ${status.state === 'connected' ? 'ogs-view__status--connected' : ''} ${
            status.state === 'error' ? 'ogs-view__status--error' : ''
          }`}
          aria-live="polite"
        >
          <span className="ogs-view__status-dot" />
          <strong>{statusCopy(status)}</strong>
        </div>
        <p className="ogs-view__feedback" aria-live="polite">
          {feedback}
        </p>

        <div className="ogs-view__launch-actions">
          <button type="button" className="ogs-view__launch" onClick={launchSimulator}>
            Launch OpenGolfSim
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>

      <aside className="ogs-view__flow" aria-label="How Golf One connects to OpenGolfSim">
        <span className="ogs-view__flow-label">LIVE CONNECTION</span>
        <div className="ogs-view__flow-step">
          <span>01</span>
          <div>
            <strong>Golf One measures</strong>
            <p>Ball speed, launch direction, launch angle, spin, and spin axis.</p>
          </div>
        </div>
        <div className="ogs-view__flow-line" />
        <div className="ogs-view__flow-step">
          <span>02</span>
          <div>
            <strong>The Pi sends one shot</strong>
            <p>The local game bridge prevents duplicate shots and waits until the course is ready.</p>
          </div>
        </div>
        <div className="ogs-view__flow-line" />
        <div className="ogs-view__flow-step">
          <span>03</span>
          <div>
            <strong>OpenGolfSim plays it</strong>
            <p>Sign in, choose a course, and use the Golf One chip to confirm or send a mock test shot.</p>
          </div>
        </div>
        <p className="ogs-view__exit-note">
          To return to the Pi desktop: tap the top-right corner 10 times, then enter 0000.
        </p>
      </aside>
    </section>
  );
}
