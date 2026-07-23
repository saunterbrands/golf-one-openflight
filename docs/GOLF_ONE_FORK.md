# Golf One product fork

This repository is the Golf One product fork of
[`jewbetcha/openflight`](https://github.com/jewbetcha/openflight). Product
branding and Raspberry Pi kiosk optimizations live here so the upstream project
can continue to evolve independently.

## Remotes

- `origin`: `https://github.com/saunterbrands/golf-one-openflight.git`
- `upstream`: `https://github.com/jewbetcha/openflight.git`

## Bring an OpenFlight update into Golf One

Always merge upstream into a branch first so Golf One branding can be checked
before the Pi is updated:

```bash
git fetch upstream
git switch -c update/openflight-YYYY-MM-DD
git merge upstream/main
cd ui && npm ci && npm test && npm run build
git push -u origin update/openflight-YYYY-MM-DD
```

After reviewing the branch, merge it into `main`. On the Raspberry Pi:

```bash
cd /home/openflight/golf-one-openflight
git pull --ff-only origin main
cd ui && npm ci && npm run build
```

Then restart the kiosk. OpenFlight's GNU AGPLv3 license remains in place and
applies to this fork.

## Raspberry Pi product startup

Golf One's appliance entry point is:

```bash
scripts/launch-golf-one.sh
```

It opens the full stack in mock/simulator mode by default, then launches the
Golf One Live dashboard full-screen. OpenGolfSim remains available as a manual
display choice in Dashboard **Settings**. If the server is already healthy and
only Chromium was closed, the launcher reopens the persistent kiosk profile
instead of starting a duplicate server.

The Raspberry Pi desktop launcher is tracked at
`scripts/setup/GolfOne.desktop`. The custom Plymouth boot theme and protected
appliance session are installed separately: Plymouth owns early boot, then the
appliance session keeps a Golf One cover above the Pi desktop until Chromium
has painted the local loading page.

Install both pieces once on each Raspberry Pi, then reboot:

```bash
cd /home/openflight/golf-one-openflight
sudo ./scripts/setup/install-golf-one-plymouth.sh
sudo ./scripts/setup/install-golf-one-appliance-session.sh
sudo reboot
```

The Plymouth installer keeps a timestamped backup under
`/var/backups/golf-one/boot-splash-*`, selects the independent `golf-one`
Plymouth theme, suppresses Raspberry Pi firmware and kernel branding, and
rebuilds the initramfs so the splash is available during early boot. The
appliance-session installer keeps its backup under
`/var/backups/golf-one/appliance-session-*`, selects the dedicated `golf-one`
LightDM session, preserves the Waveshare touch matrix, and starts the normal Pi
desktop behind the cover so the protected 10-tap/PIN exit still works.

The expected visual handoff is:

```text
Golf One Plymouth → Golf One session cover → Golf One loading page → Live dashboard
```

The Raspberry Pi wallpaper, panel, greeter, and OpenGolfSim are not part of the
normal startup path.

The Pi owns a loopback-only OpenGolfSim shot relay, while a bundled Chromium
extension posts those shots into the active FUSE game and returns completed
results. The extension also adds Golf One status/setup, a Dashboard shortcut,
an immersive-layout toggle, and the protected exit gesture to the full-screen
game. The local Golf One UI always starts on its Live dashboard; OpenGolfSim
opens only after it is chosen manually. See
[`docs/simulator/opengolfsim.md`](simulator/opengolfsim.md) for account and shot
bridge setup.
