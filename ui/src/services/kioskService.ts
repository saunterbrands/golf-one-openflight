/**
 * Ask the local OpenFlight server to cleanly stop so the kiosk launcher can
 * close Chromium and reveal the Raspberry Pi desktop.
 */
export async function requestKioskExit(): Promise<void> {
  const response = await fetch('/api/shutdown', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Kiosk exit request failed with status ${response.status}`);
  }
}
