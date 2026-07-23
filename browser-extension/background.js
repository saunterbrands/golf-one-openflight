const GOLF_ONE_API = 'http://127.0.0.1:8080';

async function request(path, options = {}) {
  const response = await fetch(`${GOLF_ONE_API}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
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

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
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
    default:
      return false;
  }

  operation
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
