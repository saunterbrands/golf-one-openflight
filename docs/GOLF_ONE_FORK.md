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
