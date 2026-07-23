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
official OpenGolfSim Web app full-screen. If the server is already healthy and
only Chromium was closed, it reopens the persistent kiosk profile instead of
starting a duplicate server.

The Raspberry Pi desktop launcher is tracked at
`scripts/setup/GolfOne.desktop`. The custom Plymouth boot theme and installer
are under `scripts/setup/plymouth/` and
`scripts/setup/install-golf-one-plymouth.sh`.

The Pi owns the OpenGolfSim shot WebSocket, while a bundled Chromium extension
adds Golf One status/setup, a Dashboard shortcut, and the protected exit
gesture to the full-screen game. The local Golf One UI defaults to its
OpenGolfSim setup/launch view. See
[`docs/simulator/opengolfsim.md`](simulator/opengolfsim.md) for account and shot
bridge setup.
