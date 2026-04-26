# GSPro Integration

OpenFlight can stream shots to [GSPro](https://gsprogolf.com/) over the
OpenConnectV1 protocol. Optional — disabled by default.

## Setup

1. **On the GSPro PC:** open the GSPro app and start the **OpenAPI Connect**
   window (Settings → OpenAPI). Note the IP address shown.
2. **On the OpenFlight Pi:** copy the example config and edit it:
   ```bash
   cp config/gspro.example.json config/gspro.json
   ```
   Edit `config/gspro.json`:
   ```json
   {
     "enabled": true,
     "host": "192.168.1.50",
     "port": 921,
     "device_id": "OpenFlight",
     "units": "Yards",
     "heartbeat_interval_s": 5
   }
   ```
   Replace `host` with the GSPro PC's IP. Keep the port at `921` unless
   GSPro shows a different one.
3. **Start OpenFlight:** `scripts/start-kiosk.sh` will pick up the config
   automatically.

## CLI overrides

```
scripts/start-kiosk.sh --gspro 192.168.1.50          # override host, port=921
scripts/start-kiosk.sh --gspro 192.168.1.50:9000     # override host and port
scripts/start-kiosk.sh --no-gspro                    # disable even if config enabled
```

`--no-gspro` always wins. `--gspro` overrides the file host/port and forces
`enabled: true`.

## What gets sent

Every detected shot sends an OpenConnectV1 JSON message containing ball speed,
launch angles, spin (total + axis + back/side), and carry distance. When a
field is not measured by the hardware, OpenFlight fills it from a model and
tags the field as `estimated`. The shot card in the UI shows per-field
`[M]` / `[E]` badges so you can see exactly what came from radar vs. model.

| Field | Source |
|---|---|
| Ball speed | OPS243 (always measured; shot is dropped if missing) |
| HLA / VLA | KLD7 horizontal/vertical when present, else model fallback |
| Total spin | Rolling buffer when confidence ≥ 0.7, else per-club spin model |
| Spin axis | `HLA − club_path` (D-plane), else 0° |
| Carry | `Shot.estimated_carry_yards` (already a model) |
| Club speed/path | OPS243 / KLD7-horizontal when present |

See the [design spec](superpowers/specs/2026-04-26-gspro-integration-design.md)
for the full fallback table.

## Status pill

The top bar shows a `GSPro` pill: green = connected, amber =
connecting/reconnecting, gray = disabled. Hover for the host:port and last
error message.

## Putting

GSPro's putting mode (`Club: PT`) is logged but **not** specially handled in
v1 — the Doppler sound trigger is unlikely to detect a putt anyway.

## Manual verification

1. Open GSPro and start the OpenAPI Connect window.
2. Set `config/gspro.json` to point to the GSPro PC.
3. `scripts/start-kiosk.sh` — confirm the status pill goes green.
4. Hit a shot — verify it appears in GSPro and on the OpenFlight UI shot card.
5. Confirm the per-field badges match what hardware was actually connected.
