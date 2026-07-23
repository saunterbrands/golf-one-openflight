# OpenGolfSim

Golf One supports both current OpenGolfSim surfaces:

- **OpenGolfSim Web** runs full-screen on the Raspberry Pi and Waveshare panel.
  A single Pi-owned WebSocket bridge sends shots independently of the browser.
- **OpenGolfSim Desktop** on macOS or Windows can receive Golf One shots through
  its native Developer API on TCP port **3111**.

OpenGolfSim Desktop is not released for Raspberry Pi/Linux ARM. The Pi therefore
opens the official experimental WebGL simulator.

## OpenGolfSim Web on the Waveshare

1. Golf One opens `https://app.opengolfsim.com/account/simulator` at boot.
2. Sign in to OpenGolfSim. The password stays entirely inside OpenGolfSim.
3. Press the **Golf One** status chip at the lower-left.
4. Enter the same OpenGolfSim account email and press **Connect shots**.
5. When the chip reads **Shots connected**, select a range or course.

The Pi—not the webpage—owns the account-scoped connection:

```text
wss://app.opengolfsim.com/api/YOUR_ACCOUNT_EMAIL
```

This design has three useful properties:

- changing Golf One dashboard tabs cannot disconnect the round;
- opening a dashboard on a phone cannot duplicate a physical shot;
- a network outage never replays an old shot after reconnecting.

The account email is stored at
`~/.config/golf-one/opengolfsim.json` with user-only permissions. No password is
stored by Golf One.

The Golf One browser extension supplies the lower-left connection control,
Dashboard shortcut, and the protected kiosk exit on every OpenGolfSim page. Tap
the top-right corner 10 times within three seconds, enter `0000`, then press
Enter to return to the Raspberry Pi desktop.

## Dashboard controls

From the full-screen simulator, press the lower-left **Golf One** chip and then
**Dashboard**. The dashboard's Simulator tab can:

- configure or update the OpenGolfSim account email;
- display the Pi bridge's actual connection/error state;
- send an explicit mock test shot;
- relaunch OpenGolfSim full-screen.

An invalid account is shown as a permanent setup error instead of reconnecting
forever. Correct the email to retry.

## OpenGolfSim Desktop

Requirements:

- OpenGolfSim Desktop running on a Mac or Windows PC;
- **Developer API** selected as the launch monitor;
- the Pi and desktop computer on the same LAN with TCP port 3111 reachable.

Configure `config/sim.json`:

```json
{
  "connectors": [
    {
      "type": "opengolfsim",
      "enabled": true,
      "host": "192.168.1.60",
      "port": 3111,
      "units": "imperial"
    }
  ]
}
```

Then launch Golf One with TCP simulator connectors enabled:

```bash
scripts/start-kiosk.sh --sim
```

The connector retries if OpenGolfSim Desktop is not running yet.

## Native shot format

OpenGolfSim's current APIs accept native JSON rather than a GSPro/OpenConnect
envelope. Golf One announces the launch monitor at connection time:

```json
{"type":"device","status":"ready"}
```

It then sends:

```json
{
  "type": "shot",
  "unit": "imperial",
  "shot": {
    "ballSpeed": 135.0,
    "verticalLaunchAngle": 11.1,
    "horizontalLaunchAngle": 1.2,
    "spinSpeed": 4800,
    "spinAxis": 2.5
  }
}
```

The Desktop TCP API receives newline-delimited JSON. Metric TCP mode converts
mph to metres per second. Golf One also reverses spin-axis sign at the
OpenGolfSim boundary because the two systems define positive curvature in
opposite directions.

Measured values are preferred. Missing launch/spin fields use the same
club-aware fallback model for Web and Desktop.

## Course building

Course creation is a separate desktop authoring workflow; it does not run on the
Pi and is not required to connect Golf One. OpenGolfSim currently documents a
Unity project template plus terrain and mesh tools:

- [Course-building guide](https://help.opengolfsim.com/course-building/)
- [Getting started](https://help.opengolfsim.com/course-building/getting-started/)

## Troubleshooting

- **OpenGolfSim shows Log In:** sign in or create an OpenGolfSim account.
- **Setup needed / Invalid User:** the Golf One email must exactly match the
  OpenGolfSim account.
- **Connecting:** verify the Pi has internet access.
- **Desktop status stays offline:** verify the PC/Mac IP, select Developer API
  in OpenGolfSim Desktop, and allow TCP 3111 through its firewall.
- **Shot does not play:** OpenGolfSim must be on a hittable range/course screen.
- **Shot is lost while offline:** this is intentional; stale golf shots are not
  queued or replayed.

## Official references

- [OpenGolfSim Web Simulator](https://help.opengolfsim.com/web/webgl/)
- [Developer API](https://help.opengolfsim.com/desktop/apis/)
- [Shot Data API](https://help.opengolfsim.com/desktop/apis/shot-data/)
