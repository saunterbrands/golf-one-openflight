import { useEffect, useState } from 'react';
import { getServerOrigin } from '../utils/serverOrigin';
import './DisplaySettings.css';

export type DisplayPreference = 'simulator' | 'launch_monitor';

interface DisplayModeResponse {
  mode: DisplayPreference;
  url: string;
  error?: string;
}

interface DisplayOption {
  mode: DisplayPreference;
  eyebrow: string;
  name: string;
  description: string;
  destination: string;
}

const DISPLAY_OPTIONS: DisplayOption[] = [
  {
    mode: 'simulator',
    eyebrow: 'PLAY',
    name: 'OpenGolfSim Simulator',
    description: 'Open courses, practice ranges, and the full simulator while Golf One sends every measured shot.',
    destination: 'app.opengolfsim.com',
  },
  {
    mode: 'launch_monitor',
    eyebrow: 'MEASURE',
    name: 'Wide Launch Monitor',
    description: 'Show the camera, ball data, launch numbers, spin, and recent shots across the Waveshare display.',
    destination: '/display · 1920 × 720',
  },
];

const DISPLAY_MODE_API_URL = `${getServerOrigin()}/api/display-mode`;

async function saveDisplayMode(mode: DisplayPreference): Promise<DisplayModeResponse> {
  const response = await fetch(DISPLAY_MODE_API_URL, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ mode }),
  });
  const result = (await response.json()) as DisplayModeResponse;
  if (!response.ok) {
    throw new Error(result.error || 'Golf One could not save the display setting.');
  }
  return result;
}

export function DisplaySettings() {
  const [selectedMode, setSelectedMode] = useState<DisplayPreference>('simulator');
  const [savedMode, setSavedMode] = useState<DisplayPreference>('simulator');
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState('Loading the remembered display…');

  useEffect(() => {
    let active = true;

    fetch(DISPLAY_MODE_API_URL, { headers: { Accept: 'application/json' } })
      .then(async (response) => {
        const result = (await response.json()) as DisplayModeResponse;
        if (!response.ok) throw new Error(result.error || `status ${response.status}`);
        if (!active) return;
        setSelectedMode(result.mode);
        setSavedMode(result.mode);
        setFeedback('Choose a display, then select Show selected display to open it.');
      })
      .catch(() => {
        if (active) setFeedback('OpenGolfSim is ready as the remembered selection.');
      });

    return () => {
      active = false;
    };
  }, []);

  const persistSelection = async () => {
    setIsSaving(true);
    setFeedback('Saving display…');
    try {
      const result = await saveDisplayMode(selectedMode);
      setSavedMode(result.mode);
      setFeedback(
        `${DISPLAY_OPTIONS.find((option) => option.mode === result.mode)?.name} is now remembered on this Golf One. The Dashboard will still open first.`
      );
      return result;
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Golf One could not save the display setting.');
      return null;
    } finally {
      setIsSaving(false);
    }
  };

  const showSelectedDisplay = async () => {
    const result = await persistSelection();
    if (result) window.location.assign(result.url);
  };

  return (
    <section className="display-settings" aria-labelledby="display-settings-title">
      <div className="display-settings__intro">
        <span className="display-settings__mark" aria-hidden="true">
          G1
        </span>
        <p className="display-settings__eyebrow">GOLF ONE APPLIANCE</p>
        <h1 id="display-settings-title">Display Settings</h1>
        <p>
          Golf One Dashboard always starts first. Choose which full-screen display to open manually from here; this Pi
          remembers your selection for next time.
        </p>
        <div className="display-settings__screen">
          <span>WAVESHARE DISPLAY</span>
          <strong>12.3″ · 1920 × 720</strong>
        </div>
      </div>

      <div className="display-settings__chooser">
        <div className="display-settings__chooser-heading">
          <div>
            <span>DISPLAY SHORTCUT</span>
            <h2>Choose a display</h2>
          </div>
          <span className="display-settings__saved">Remembered on this Golf One</span>
        </div>

        <div className="display-settings__options" role="radiogroup" aria-label="Display selection">
          {DISPLAY_OPTIONS.map((option) => {
            const selected = selectedMode === option.mode;
            const saved = savedMode === option.mode;
            return (
              <button
                key={option.mode}
                type="button"
                className={`display-settings__option ${selected ? 'display-settings__option--selected' : ''}`}
                role="radio"
                aria-checked={selected}
                onClick={() => setSelectedMode(option.mode)}
              >
                <span className="display-settings__option-topline">
                  <span>{option.eyebrow}</span>
                  {saved && <strong>Remembered</strong>}
                </span>
                <span className="display-settings__option-name">{option.name}</span>
                <span className="display-settings__option-description">{option.description}</span>
                <span className="display-settings__option-destination">{option.destination}</span>
              </button>
            );
          })}
        </div>

        <p className="display-settings__feedback" aria-live="polite">
          {feedback}
        </p>

        <div className="display-settings__actions">
          <button type="button" className="display-settings__save" disabled={isSaving} onClick={persistSelection}>
            {isSaving ? 'Saving…' : 'Remember selection'}
          </button>
          <button type="button" className="display-settings__show" disabled={isSaving} onClick={showSelectedDisplay}>
            Show selected display
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>
    </section>
  );
}

export function DisplaySettingsLink() {
  return (
    <button
      type="button"
      className="display-settings-link"
      aria-label="Open display settings"
      onClick={() => window.location.assign('/?settings=1')}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.5 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.5a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.5 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.15.37.36.7.65.98.3.28.68.42 1.1.42H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z" />
      </svg>
      <span>Settings</span>
    </button>
  );
}
