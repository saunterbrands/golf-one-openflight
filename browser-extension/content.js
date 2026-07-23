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

      .golf-one-save {
        grid-column: 1 / -1;
      }

      .golf-one-game-action {
        grid-column: 1 / -1;
      }

      .golf-one-game-action[hidden] {
        display: none;
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
      <p class="golf-one-eyebrow">Display settings</p>
      <h2>Golf One Settings</h2>
      <p class="golf-one-copy">
        Golf One sends measured shots directly into the open course on this Pi. The email below is an optional
        compatibility relay for older OpenGolfSim Web versions.
      </p>
      <label class="golf-one-label" for="golf-one-email">Optional OpenGolfSim relay email</label>
      <input class="golf-one-input golf-one-email" id="golf-one-email" type="email" inputmode="email" autocomplete="email" />
      <div class="golf-one-actions">
        <button class="golf-one-button golf-one-dashboard" type="button">Dashboard</button>
        <button class="golf-one-button golf-one-settings" type="button">Display settings</button>
        <button class="golf-one-button golf-one-button--primary golf-one-save" type="button">Save fallback</button>
        <button class="golf-one-button golf-one-game-action golf-one-test-shot" type="button" hidden>Send test shot</button>
        <button class="golf-one-button golf-one-game-action golf-one-game-controls" type="button" hidden>
          Show OpenGolfSim controls
        </button>
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
  const settings = root.querySelector('.golf-one-settings');
  const hotspot = root.querySelector('.golf-one-hotspot');
  const exitOverlay = root.querySelector('.golf-one-exit');
  const exitForm = root.querySelector('.golf-one-exit-form');
  const exitPin = root.querySelector('.golf-one-pin');
  const exitMessage = root.querySelector('.golf-one-exit-message');
  const cancel = root.querySelector('.golf-one-cancel');
  const testShot = root.querySelector('.golf-one-test-shot');
  const gameControls = root.querySelector('.golf-one-game-controls');

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

  let gameFrame = null;
  let gameSessionId = '';
  let gameCursor = 0;
  let gamePollRunning = false;
  let gameSessionOpening = false;
  let inFlightShot = null;
  let layoutSnapshot = null;
  let immersiveLayout = true;
  let directRangeRecoveryTimer = 0;
  const DIRECT_RANGE_RECOVERY_MS = 15000;
  const directRangeVerification =
    window.location.pathname === '/fuse/examples/range/index.html' &&
    new URLSearchParams(window.location.search).get('golf-one-test') === '1';

  const setGameState = (label, connectionState = 'connected') => {
    state.dataset.state = connectionState;
    state.textContent = label;
  };

  const findGameFrame = () => document.querySelector('iframe[title="fuse"]');

  const applyOpenGolfSimLayout = () => {
    gameFrame = findGameFrame();
    if (!gameFrame) return;

    const gameMain = gameFrame.closest('main');
    const drawer = gameMain?.parentElement?.querySelector('.MuiDrawer-root') || null;
    if (!layoutSnapshot) {
      layoutSnapshot = [drawer, gameMain, gameFrame]
        .filter(Boolean)
        .map((element) => ({
          element,
          style: element.getAttribute('style'),
        }));
    }

    if (immersiveLayout) {
      drawer?.style.setProperty('display', 'none', 'important');
      gameMain?.style.setProperty('margin-left', '0px', 'important');
      gameMain?.style.setProperty('width', '100vw', 'important');
      gameFrame.style.setProperty('width', '100vw', 'important');
      gameFrame.style.setProperty('height', '100vh', 'important');
      gameControls.textContent = 'Show OpenGolfSim controls';
    }
    gameControls.hidden = false;
    testShot.hidden = false;
  };

  const restoreOpenGolfSimLayout = () => {
    for (const snapshot of layoutSnapshot || []) {
      if (snapshot.style === null) {
        snapshot.element.removeAttribute('style');
      } else {
        snapshot.element.setAttribute('style', snapshot.style);
      }
    }
    gameControls.textContent = 'Hide OpenGolfSim controls';
  };

  const shotsMatch = (expected, actual) => {
    if (!expected || !actual) return false;
    const fields = [
      'ballSpeed',
      'verticalLaunchAngle',
      'horizontalLaunchAngle',
      'spinSpeed',
      'spinAxis',
    ];
    return fields.every(
      (field) =>
        Number.isFinite(Number(expected[field])) &&
        Number.isFinite(Number(actual[field])) &&
        Math.abs(Number(expected[field]) - Number(actual[field])) <= 0.11
    );
  };

  const acknowledgeGameShot = async (sequence, deliveryState, result) =>
    send({
      type: 'golf-one-game-ack',
      sessionId: gameSessionId,
      sequence,
      state: deliveryState,
      result,
    });

  const closeGameSession = async (reason) => {
    const closingSessionId = gameSessionId;
    gameSessionId = '';
    gameSessionOpening = false;
    inFlightShot = null;
    if (directRangeRecoveryTimer) {
      window.clearTimeout(directRangeRecoveryTimer);
      directRangeRecoveryTimer = 0;
    }
    if (closingSessionId) {
      await send({
        type: 'golf-one-game-session',
        state: 'closed',
        sessionId: closingSessionId,
      });
    }
    if (reason === 'iframe-removed') {
      setGameState('Open a course');
    }
  };

  const pollGameShots = async () => {
    if (gamePollRunning || !gameSessionId) return;
    gamePollRunning = true;

    while (gameSessionId) {
      const sessionAtPollStart = gameSessionId;
      const response = await send({
        type: 'golf-one-game-poll',
        sessionId: sessionAtPollStart,
        after: gameCursor,
      });
      if (!gameSessionId || gameSessionId !== sessionAtPollStart) break;
      if (!response.ok) {
        setGameState('Bridge offline', 'error');
        gameSessionId = '';
        break;
      }

      for (const delivery of response.data?.shots || []) {
        const sequence = delivery?.sequence;
        const shot = delivery?.payload?.shot;
        if (!Number.isInteger(sequence) || !shot) continue;

        try {
          if (directRangeVerification) {
            window.postMessage({ type: 'shot', shot }, window.location.origin);
          } else {
            gameFrame = findGameFrame();
            if (!gameFrame?.contentWindow) throw new Error('OpenGolfSim game frame closed');
            const targetOrigin = new URL(gameFrame.src).origin;
            gameFrame.contentWindow.postMessage({ type: 'shot', shot }, targetOrigin);
          }
          gameCursor = sequence;
          inFlightShot = { sequence, shot };
          setGameState('Shot in play');
          const acknowledged = await acknowledgeGameShot(sequence, 'posted');
          if (!acknowledged.ok) {
            throw new Error(acknowledged.error || 'Golf One could not confirm delivery');
          }
          if (directRangeVerification) {
            directRangeRecoveryTimer = window.setTimeout(() => {
              if (inFlightShot?.sequence !== sequence) return;
              inFlightShot = null;
              void acknowledgeGameShot(sequence, 'error').then(() => {
                setGameState('Visual test ready');
              });
            }, DIRECT_RANGE_RECOVERY_MS);
          }
        } catch (error) {
          gameCursor = sequence;
          if (inFlightShot?.sequence === sequence) inFlightShot = null;
          await acknowledgeGameShot(sequence, 'error');
          setGameState('Shot not delivered', 'error');
          message.textContent =
            error instanceof Error ? error.message : 'Golf One could not deliver the shot.';
        }
      }
    }
    gamePollRunning = false;
  };

  const openGameSession = async () => {
    if (gameSessionOpening) return;
    gameSessionOpening = true;
    const response = await send({
      type: 'golf-one-game-session',
      state: 'ready',
      sessionId: gameSessionId || undefined,
    });
    gameSessionOpening = false;
    if (!response.ok) {
      setGameState('Bridge offline', 'error');
      return;
    }

    gameSessionId = response.data.session_id;
    gameCursor = response.data.cursor ?? gameCursor;
    setGameState('Game ready');
    testShot.hidden = false;
    void pollGameShots();
  };

  window.addEventListener('message', (event) => {
    if (directRangeVerification) return;
    gameFrame = findGameFrame();
    if (!gameFrame || event.source !== gameFrame.contentWindow) return;
    if (!event.data || typeof event.data !== 'object') return;

    if (event.data.type === 'ready') {
      applyOpenGolfSimLayout();
      setGameState('Loading course');
      return;
    }
    if (event.data.type === 'player') {
      void openGameSession();
      return;
    }
    if (event.data.type === 'result' && inFlightShot) {
      if (!shotsMatch(inFlightShot.shot, event.data.shot)) return;
      const sequence = inFlightShot.sequence;
      if (directRangeRecoveryTimer) {
        window.clearTimeout(directRangeRecoveryTimer);
        directRangeRecoveryTimer = 0;
      }
      const result = {
        ...(event.data.data || {}),
        ...(typeof event.data.surface === 'string' ? { surface: event.data.surface } : {}),
      };
      inFlightShot = null;
      void acknowledgeGameShot(sequence, 'completed', result).then((response) => {
        if (response.ok) {
          const carry = Number(result.carry);
          setGameState(Number.isFinite(carry) ? `${Math.round(carry)} yd complete` : 'Game ready');
        }
      });
    }
  });

  const watchForGame = new MutationObserver(() => {
    const nextFrame = findGameFrame();
    if (gameFrame && !nextFrame) {
      restoreOpenGolfSimLayout();
      layoutSnapshot = null;
      gameFrame = null;
      gameControls.hidden = true;
      testShot.hidden = true;
      void closeGameSession('iframe-removed');
      return;
    }
    if (!nextFrame) return;
    if (gameFrame && gameFrame !== nextFrame) {
      restoreOpenGolfSimLayout();
      layoutSnapshot = null;
      void closeGameSession('iframe-replaced');
    }
    gameFrame = nextFrame;
    applyOpenGolfSimLayout();
  });
  watchForGame.observe(document.documentElement, { childList: true, subtree: true });
  applyOpenGolfSimLayout();

  if (directRangeVerification) {
    const waitForRange = window.setInterval(() => {
      if (!document.querySelector('canvas')) return;
      window.clearInterval(waitForRange);
      window.setTimeout(() => void openGameSession(), 6000);
    }, 250);
  }

  const renderStatus = (status) => {
    const connectionState = status?.state || 'disconnected';
    const browserState = status?.browser?.game_state;
    const completedCarry = Number(status?.browser?.last_delivery?.result?.carry);
    state.dataset.state = connectionState;
    state.textContent =
      status?.browser?.active && browserState === 'ready'
        ? Number.isFinite(completedCarry)
          ? `${Math.round(completedCarry)} yd complete`
          : 'Game ready'
        : status?.browser?.active && (browserState === 'queued' || browserState === 'in_flight')
          ? 'Shot in play'
          : connectionState === 'connected'
            ? 'Shots connected'
        : connectionState === 'error'
          ? 'Setup needed'
          : connectionState === 'connecting' || connectionState === 'reconnecting'
            ? 'Connecting'
            : status?.configured
              ? 'Offline'
              : 'Open a course';
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

  settings.addEventListener('click', () => {
    window.location.assign('http://127.0.0.1:8080/?settings=1');
  });

  gameControls.addEventListener('click', () => {
    immersiveLayout = !immersiveLayout;
    if (immersiveLayout) {
      applyOpenGolfSimLayout();
    } else {
      restoreOpenGolfSimLayout();
    }
  });

  testShot.addEventListener('click', async () => {
    testShot.disabled = true;
    message.textContent = 'Sending a Golf One test shot…';
    const response = await send({ type: 'golf-one-game-test-shot' });
    testShot.disabled = false;
    message.textContent = response.ok
      ? 'Test shot measured. Watch the OpenGolfSim ball flight.'
      : response.error || 'Golf One could not generate a test shot.';
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

  window.addEventListener('pagehide', () => {
    if (!gameSessionId) return;
    void closeGameSession('pagehide');
  });

  refreshStatus();
  window.setInterval(refreshStatus, 5000);
})();
