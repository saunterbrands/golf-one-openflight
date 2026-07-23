(() => {
  if (document.getElementById('golf-one-simulator-controls')) return;

  const host = document.createElement('div');
  host.id = 'golf-one-simulator-controls';
  document.documentElement.appendChild(host);
  const root = host.attachShadow({ mode: 'closed' });

  root.innerHTML = `
    <style>
      :host {
        --go-green: #96e647;
        --go-deep: #06110c;
        --go-panel: rgba(8, 24, 16, 0.97);
        --go-cream: #f6f4ed;
        --go-muted: #a9b8ae;
        all: initial;
      }

      *, *::before, *::after { box-sizing: border-box; }

      button, input {
        font: 800 13px/1.1 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      .golf-one-chip {
        position: fixed;
        left: 16px;
        bottom: 14px;
        z-index: 2147483645;
        display: flex;
        align-items: center;
        gap: 9px;
        min-height: 42px;
        padding: 0 14px 0 11px;
        border: 1px solid rgba(150, 230, 71, 0.38);
        border-radius: 999px;
        background: rgba(6, 17, 12, 0.9);
        color: var(--go-cream);
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.38);
        backdrop-filter: blur(12px);
        cursor: pointer;
      }

      .golf-one-mark {
        display: grid;
        width: 24px;
        height: 24px;
        place-items: center;
        border: 2px solid var(--go-green);
        border-radius: 50%;
        color: var(--go-green);
        font-size: 11px;
        letter-spacing: -0.08em;
      }

      .golf-one-name {
        font-size: 13px;
        letter-spacing: 0.01em;
      }

      .golf-one-state {
        display: flex;
        align-items: center;
        gap: 6px;
        color: var(--go-muted);
        font-size: 10px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }

      .golf-one-state::before {
        content: "";
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #ffbd4a;
        box-shadow: 0 0 8px rgba(255, 189, 74, 0.65);
      }

      .golf-one-state[data-state="connected"] {
        color: var(--go-green);
      }

      .golf-one-state[data-state="connected"]::before {
        background: var(--go-green);
        box-shadow: 0 0 9px rgba(150, 230, 71, 0.72);
      }

      .golf-one-panel {
        position: fixed;
        left: 16px;
        bottom: 66px;
        z-index: 2147483645;
        width: min(390px, calc(100vw - 32px));
        padding: 20px;
        border: 1px solid rgba(150, 230, 71, 0.28);
        border-radius: 18px;
        background: var(--go-panel);
        color: var(--go-cream);
        box-shadow: 0 24px 70px rgba(0, 0, 0, 0.58);
        backdrop-filter: blur(16px);
      }

      .golf-one-panel[hidden], .golf-one-exit[hidden] { display: none; }

      .golf-one-eyebrow {
        margin: 0 0 6px;
        color: var(--go-green);
        font: 900 10px/1.2 Inter, ui-sans-serif, system-ui, sans-serif;
        letter-spacing: 0.16em;
        text-transform: uppercase;
      }

      .golf-one-panel h2, .golf-one-exit-card h2 {
        margin: 0;
        color: var(--go-cream);
        font: 900 24px/1 Inter, ui-sans-serif, system-ui, sans-serif;
        letter-spacing: -0.04em;
      }

      .golf-one-copy {
        margin: 10px 0 16px;
        color: var(--go-muted);
        font: 700 12px/1.5 Inter, ui-sans-serif, system-ui, sans-serif;
      }

      .golf-one-label {
        display: block;
        margin-bottom: 7px;
        color: var(--go-muted);
        font: 900 10px/1.2 Inter, ui-sans-serif, system-ui, sans-serif;
        letter-spacing: 0.1em;
        text-transform: uppercase;
      }

      .golf-one-input {
        width: 100%;
        height: 46px;
        padding: 0 12px;
        border: 1px solid rgba(246, 244, 237, 0.18);
        border-radius: 10px;
        outline: 0;
        background: rgba(0, 0, 0, 0.3);
        color: var(--go-cream);
      }

      .golf-one-input:focus {
        border-color: var(--go-green);
        box-shadow: 0 0 0 3px rgba(150, 230, 71, 0.13);
      }

      .golf-one-actions {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 9px;
        margin-top: 12px;
      }

      .golf-one-button {
        min-height: 44px;
        padding: 0 13px;
        border: 1px solid rgba(246, 244, 237, 0.16);
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.05);
        color: var(--go-cream);
        cursor: pointer;
      }

      .golf-one-button--primary {
        border-color: var(--go-green);
        background: var(--go-green);
        color: var(--go-deep);
      }

      .golf-one-message {
        min-height: 18px;
        margin: 10px 0 0;
        color: var(--go-muted);
        font: 800 11px/1.4 Inter, ui-sans-serif, system-ui, sans-serif;
      }

      .golf-one-hotspot {
        position: fixed;
        top: 0;
        right: 0;
        z-index: 2147483646;
        width: 64px;
        height: 64px;
        padding: 0;
        border: 0;
        background: transparent;
        opacity: 0;
        cursor: default;
      }

      .golf-one-exit {
        position: fixed;
        inset: 0;
        z-index: 2147483647;
        display: grid;
        padding: 20px;
        place-items: center;
        background: radial-gradient(circle at 50% 35%, rgba(150, 230, 71, 0.16), transparent 32rem), rgba(1, 7, 4, 0.93);
        backdrop-filter: blur(14px);
      }

      .golf-one-exit-card {
        width: min(430px, 100%);
        padding: 34px;
        border: 1px solid rgba(150, 230, 71, 0.28);
        border-radius: 20px;
        background: linear-gradient(155deg, rgba(23, 58, 48, 0.99), rgba(6, 17, 12, 0.99));
        color: var(--go-cream);
        box-shadow: 0 28px 80px rgba(0, 0, 0, 0.68);
      }

      .golf-one-pin {
        margin-top: 18px;
        height: 64px;
        font-size: 28px;
        letter-spacing: 0.5em;
        text-align: center;
      }

      @media (max-height: 540px) {
        .golf-one-exit-card { padding: 22px; }
        .golf-one-pin { height: 52px; }
      }
    </style>

    <button class="golf-one-chip" type="button" aria-expanded="false">
      <span class="golf-one-mark" aria-hidden="true">G1</span>
      <span class="golf-one-name">Golf One</span>
      <span class="golf-one-state" data-state="loading">Checking</span>
    </button>

    <section class="golf-one-panel" aria-label="Golf One simulator connection" hidden>
      <p class="golf-one-eyebrow">Simulator control</p>
      <h2>Golf One</h2>
      <p class="golf-one-copy">
        Use the same email as this OpenGolfSim account so Golf One can send each measured shot into the course.
      </p>
      <label class="golf-one-label" for="golf-one-email">OpenGolfSim email</label>
      <input class="golf-one-input golf-one-email" id="golf-one-email" type="email" inputmode="email" autocomplete="email" />
      <div class="golf-one-actions">
        <button class="golf-one-button golf-one-dashboard" type="button">Dashboard</button>
        <button class="golf-one-button golf-one-button--primary golf-one-save" type="button">Connect shots</button>
      </div>
      <p class="golf-one-message" aria-live="polite"></p>
    </section>

    <button class="golf-one-hotspot" type="button" aria-label="Open Golf One kiosk exit"></button>

    <div class="golf-one-exit" hidden>
      <section class="golf-one-exit-card" role="dialog" aria-modal="true" aria-labelledby="golf-one-exit-title">
        <p class="golf-one-eyebrow">System access</p>
        <h2 id="golf-one-exit-title">Exit to desktop</h2>
        <p class="golf-one-copy">Enter the four-digit administrator PIN to close Golf One.</p>
        <form class="golf-one-exit-form">
          <label class="golf-one-label" for="golf-one-pin">Administrator PIN</label>
          <input class="golf-one-input golf-one-pin" id="golf-one-pin" type="password" inputmode="numeric" maxlength="4" autocomplete="off" />
          <p class="golf-one-message golf-one-exit-message" aria-live="polite"></p>
          <div class="golf-one-actions">
            <button class="golf-one-button golf-one-cancel" type="button">Cancel</button>
            <button class="golf-one-button golf-one-button--primary" type="submit">Exit Golf One</button>
          </div>
        </form>
      </section>
    </div>
  `;

  const chip = root.querySelector('.golf-one-chip');
  const state = root.querySelector('.golf-one-state');
  const panel = root.querySelector('.golf-one-panel');
  const email = root.querySelector('.golf-one-email');
  const save = root.querySelector('.golf-one-save');
  const message = root.querySelector('.golf-one-message');
  const dashboard = root.querySelector('.golf-one-dashboard');
  const hotspot = root.querySelector('.golf-one-hotspot');
  const exitOverlay = root.querySelector('.golf-one-exit');
  const exitForm = root.querySelector('.golf-one-exit-form');
  const exitPin = root.querySelector('.golf-one-pin');
  const exitMessage = root.querySelector('.golf-one-exit-message');
  const cancel = root.querySelector('.golf-one-cancel');

  const send = (payload) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage(payload, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response || { ok: false, error: 'Golf One did not respond' });
      });
    });

  const renderStatus = (status) => {
    const connectionState = status?.state || 'disconnected';
    state.dataset.state = connectionState;
    state.textContent =
      connectionState === 'connected'
        ? 'Shots connected'
        : connectionState === 'error'
          ? 'Setup needed'
          : connectionState === 'connecting' || connectionState === 'reconnecting'
            ? 'Connecting'
            : status?.configured
              ? 'Offline'
              : 'Setup needed';
    if (status?.email && !email.value) email.value = status.email;
  };

  const refreshStatus = async () => {
    const response = await send({ type: 'golf-one-status' });
    if (response.ok) {
      renderStatus(response.data);
    } else {
      state.dataset.state = 'error';
      state.textContent = 'Golf One offline';
    }
  };

  chip.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    chip.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) refreshStatus();
  });

  dashboard.addEventListener('click', () => {
    window.location.assign('http://127.0.0.1:8080');
  });

  save.addEventListener('click', async () => {
    const normalizedEmail = email.value.trim();
    if (!normalizedEmail) {
      message.textContent = 'Enter your OpenGolfSim account email.';
      email.focus();
      return;
    }

    save.disabled = true;
    message.textContent = 'Connecting Golf One…';
    const response = await send({ type: 'golf-one-configure', email: normalizedEmail });
    save.disabled = false;
    if (!response.ok) {
      message.textContent = response.error || 'Could not save the OpenGolfSim account.';
      return;
    }
    message.textContent = 'Saved. Golf One is connecting the shot bridge.';
    renderStatus(response.data);
    window.setTimeout(refreshStatus, 1200);
  });

  let taps = 0;
  let tapStartedAt = 0;
  hotspot.addEventListener('click', () => {
    const now = Date.now();
    if (!tapStartedAt || now - tapStartedAt > 3000) {
      taps = 1;
      tapStartedAt = now;
    } else {
      taps += 1;
    }

    if (taps >= 10) {
      taps = 0;
      tapStartedAt = 0;
      exitPin.value = '';
      exitMessage.textContent = '';
      exitOverlay.hidden = false;
      exitPin.focus();
    }
  });

  const closeExit = () => {
    exitOverlay.hidden = true;
    exitPin.value = '';
    exitMessage.textContent = '';
  };

  cancel.addEventListener('click', closeExit);
  exitOverlay.addEventListener('click', (event) => {
    if (event.target === exitOverlay) closeExit();
  });

  exitForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (exitPin.value !== '0000') {
      exitPin.value = '';
      exitMessage.textContent = 'That PIN is not correct. Try again.';
      exitPin.focus();
      return;
    }

    exitMessage.textContent = 'Opening the Raspberry Pi desktop…';
    const response = await send({ type: 'golf-one-shutdown' });
    if (!response.ok) {
      exitMessage.textContent = response.error || 'Golf One could not open the desktop.';
      exitPin.focus();
    }
  });

  refreshStatus();
  window.setInterval(refreshStatus, 5000);
})();
