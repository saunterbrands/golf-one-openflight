const GOLF_ONE_API = 'http://127.0.0.1:8080';

async function request(path, options = {}) {
  const response = await fetch(`${GOLF_ONE_API}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      'X-Golf-One-Extension': 'browser-relay-v1',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new Error(data.error || `Golf One returned ${response.status}`);
  }
  return data;
}

function isOpenGolfSimSender(sender) {
  try {
    const senderUrl = sender?.origin || sender?.url || sender?.tab?.url || '';
    return new URL(senderUrl).origin === 'https://app.opengolfsim.com';
  } catch {
    return false;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  let operation;

  switch (message?.type) {
    case 'golf-one-status':
      operation = request('/api/opengolfsim');
      break;
    case 'golf-one-configure':
      operation = request('/api/opengolfsim', {
        method: 'POST',
        body: JSON.stringify({ email: message.email }),
      });
      break;
    case 'golf-one-shutdown':
      operation = request('/api/shutdown', { method: 'POST' });
      break;
    case 'golf-one-game-session':
      if (!isOpenGolfSimSender(sender)) return false;
      operation = request('/api/opengolfsim/browser/session', {
        method: 'POST',
        body: JSON.stringify({
          state: message.state,
          session_id: message.sessionId,
        }),
      });
      break;
    case 'golf-one-game-poll':
      if (!isOpenGolfSimSender(sender)) return false;
      operation = request('/api/opengolfsim/browser/poll', {
        method: 'POST',
        body: JSON.stringify({
          session_id: message.sessionId,
          after: message.after,
        }),
      });
      break;
    case 'golf-one-game-ack':
      if (!isOpenGolfSimSender(sender)) return false;
      operation = request('/api/opengolfsim/browser/ack', {
        method: 'POST',
        body: JSON.stringify({
          session_id: message.sessionId,
          sequence: message.sequence,
          state: message.state,
          result: message.result,
        }),
      });
      break;
    case 'golf-one-game-test-shot':
      if (!isOpenGolfSimSender(sender)) return false;
      operation = request('/api/opengolfsim/browser/test-shot', {
        method: 'POST',
      });
      break;
    default:
      return false;
  }

  operation
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
