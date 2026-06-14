# OpenGolfSim OpenConnect plugin — with club sync

A small fork of [OpenGolfSim/ogs-plugin-openconnect](https://github.com/OpenGolfSim/ogs-plugin-openconnect)
that adds **club sync** on top of the stock shot bridge.

## Why

OpenGolfSim's launch-monitor input is shot-only — the stock OpenConnect plugin
forwards shots into OGS but never tells the connected device which club is
selected, and the native API doesn't expose club to a device either. But the
OGS **plugin SDK** fires a `shotData.on('club', clubId => …)` event whenever the
club changes in OGS. This fork listens for it and forwards the club to the
launch monitor as an OpenConnect V1 `201` player message:

```json
{ "Code": 201, "Message": "Player updated", "Player": { "Club": "I7" } }
```

OpenFlight's GSPro connector already parses `201` player messages, so the club
selected in OpenGolfSim now shows up in OpenFlight (and drives its carry/spin
model). Shots flow LM → OGS exactly as before.

## What changed vs upstream

- Subscribe to the SDK `club` event and write a `201` player update to the
  connected socket (with listener teardown on disconnect).
- `ogsToOpenConnectClub()` maps OGS club ids (`7I`, `3W`, `5H`, `DR`, `PW`…) to
  OpenConnect codes (`I7`, `W3`, `H5`, `DR`, `PW`…). Unknown ids pass through
  and are logged, so any mismatch is easy to spot and extend.
- Everything else is byte-for-byte upstream.

## Install

Copy this folder into the OpenGolfSim plugins directory (replacing the stock
OpenConnect plugin if present, so they don't both bind port 921):

- **macOS:** `~/Library/Application Support/opengolfsim-desktop/plugins/`
- **Windows:** `%USERPROFILE%\AppData\Roaming\opengolfsim-desktop\plugins\`

Restart OpenGolfSim. You should see `OpenConnect v1 + Club Sync` in its plugin
list and a log line `Listening for OpenConnect V1 clients at 127.0.0.1:921`.

## Use from OpenFlight

Configure OpenFlight's **OpenGolfSim** connector with the **openconnect**
transport (port 921) — not the `native`/3111 transport; use one or the other,
not both, or OGS gets duplicate shots. In `config/sim.json`:

```json
{
  "connectors": [
    { "type": "opengolfsim", "transport": "openconnect", "enabled": true, "host": "127.0.0.1", "port": 921 }
  ]
}
```

(The openconnect transport speaks the shared OpenConnect V1 codec under the
hood, but reports as OpenGolfSim in the config, UI, and logs.)

Now: shots stream LM → OGS, and changing the club in OGS updates OpenFlight's
club picker. See `docs/simulator/opengolfsim.md`.

## Notes / limitations

- The `club` event fires on *change*, and the SDK has no "current club" getter,
  so OpenFlight syncs on the first club change after connecting (change the club
  once, or it follows from then on).
- If a club logs as unrecognized in OGS, note the raw id from the plugin log and
  extend `ogsToOpenConnectClub()` — the OGS club-id vocabulary isn't fully
  documented.
- Worth offering upstream as a PR once validated.
