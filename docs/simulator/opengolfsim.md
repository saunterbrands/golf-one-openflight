# OpenGolfSim

Golf One supports both current OpenGolfSim surfaces:

- **OpenGolfSim Web** runs full-screen on the Raspberry Pi and Waveshare panel.
  The bundled Chromium extension sends each Pi-resolved shot directly into the
  active FUSE game frame and reports the completed result.
- **OpenGolfSim Desktop** on macOS or Windows can receive Golf One shots through
  its native Developer API on TCP port **3111**.

OpenGolfSim Desktop is not released for Raspberry Pi/Linux ARM. The Pi therefore
opens the official experimental WebGL simulator.

## OpenGolfSim Web on the Waveshare

1. Golf One checks whether `https://app.opengolfsim.com/account/simulator` is
   reachable at boot.
2. When online, Golf One opens the official hosted simulator.
3. When offline, Golf One opens the appliance-local FUSE Practice Range.
4. Sign in to OpenGolfSim when the hosted site asks. The dedicated Chromium
   profile persists the official session cookie across kiosk and Pi restarts.
5. Select a range or course.
6. Wait for the lower-left **Golf One** chip to read **Game ready**.
7. Hit a ball. In mock mode, open the chip and press **Send test shot**.

Golf One does not implement or automate OpenGolfSim authentication. The current
hosted site supports email/password login, not OAuth or passkeys. If OpenGolfSim
adds passkeys later, they can appear through its official login page without
Golf One storing an account secret.

The password stays entirely inside OpenGolfSim. Golf One does not save it in
source code, local JSON, system services, or Git. The persistent browser profile
is:

```text
~/.config/golf-one-kiosk/chromium
```

Do not delete that directory unless intentionally clearing the appliance login.

## Offline Practice Range

The local Practice Range is a separate, account-free FUSE runtime. It is not an
offline copy of the hosted account or course library. Install it once while the
Pi has internet access:

```bash
scripts/setup/install-offline-fuse-range.sh
```

The installer:

- fetches the pinned official FUSE source commit;
- builds only the Practice Range;
- copies its static runtime and required license into
  `~/.local/share/golf-one/fuse`;
- keeps all third-party FUSE code and assets outside this Git repository.

Open it directly at:

```text
http://127.0.0.1:8080/offline-simulator
```

The normal `/simulator/launch` page prefers the hosted simulator and falls back
to this local range after an offline/timeout result. The same Golf One browser
relay sends measured shots into both runtimes.

Only the official Practice Range is installed. Hosted account courses are not
silently copied. A user-authored course can be made local later only when its
GLB and related assets are licensed for that use.

The FUSE repository uses the PolyForm Noncommercial license and requires its
notice. Personal prototype/testing use is permitted; shipping this runtime in a
commercial Golf One product requires a commercial agreement with OpenGolfSim.

## Hosted simulator workflow

1. Golf One opens `https://app.opengolfsim.com/account/simulator`.
2. Sign in to OpenGolfSim. The password stays entirely inside OpenGolfSim.
3. Select a range or course.
4. Wait for the lower-left **Golf One** chip to read **Game ready**.
5. Hit a ball. In mock mode, open the chip and press **Send test shot**.

The current OpenGolfSim Web app passes shots to its FUSE iframe with
`window.postMessage`. Golf One follows that same native path:

```text
Golf One shot pipeline
        │
        ▼
loopback-only browser relay
        │
        ▼
Golf One Chromium extension
        │  postMessage({type: "shot", shot: ...})
        ▼
OpenGolfSim FUSE iframe
        │  {type: "result", data: ...}
        └──────────────────────────────► Golf One delivery status
```

This design has three useful properties:

- only the course open on the Pi can claim the local game session;
- a second shot is rejected while the previous ball is still in flight;
- reloads, expired sessions, and network outages never replay an old shot.

The extension waits for FUSE's `player` event, which occurs after the course and
ball are usable. A successful `postMessage` is shown as **Shot in play**; a
matching FUSE `result` is the end-to-end completion proof.

The Golf One browser extension supplies the lower-left connection control,
Dashboard shortcut, mock test-shot button, immersive-layout toggle, and the
protected kiosk exit on every OpenGolfSim page. The official 320-pixel manual
shot drawer is hidden by default so the game uses the full 1920×720 Waveshare
panel; **Show OpenGolfSim controls** restores it. Tap the top-right corner 10
times within three seconds, enter `0000`, then press Enter to return to the
Raspberry Pi desktop.

The account-email field is retained only as a compatibility fallback for older
OpenGolfSim Web versions that consume the documented account WebSocket. It is
not required for the local FUSE bridge. If entered, it is stored at
`~/.config/golf-one/opengolfsim.json` with user-only permissions. Golf One never
stores the OpenGolfSim password.

## Dashboard controls

From the full-screen simulator, press the lower-left **Golf One** chip and then
**Dashboard**. The dashboard's Simulator tab can:

- display the active game's actual ready/in-flight/completed state;
- configure an optional legacy WebSocket relay email;
- relaunch OpenGolfSim full-screen.

Mock test shots are intentionally available from the Golf One chip only while a
course is open, so the visual result and delivery state can be checked together.

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

OpenGolfSim FUSE is published under the PolyForm Noncommercial license. A Golf
One product or other revenue-generating deployment needs commercial permission
from OpenGolfSim; this repository's integration does not grant that permission.

## Troubleshooting

- **OpenGolfSim shows Log In:** sign in or create an OpenGolfSim account.
- **Chip says Loading course:** wait for the FUSE course and ball to initialize.
- **Chip never says Game ready:** reload the course and verify the Golf One
  Chromium extension is enabled.
- **Optional relay says Invalid User:** the saved fallback email must exactly
  match the OpenGolfSim account.
- **Desktop status stays offline:** verify the PC/Mac IP, select Developer API
  in OpenGolfSim Desktop, and allow TCP 3111 through its firewall.
- **Shot does not play:** the chip must say **Game ready** before impact.
- **Shot is lost while offline:** this is intentional; stale golf shots are not
  queued or replayed.

## Official references

- [OpenGolfSim Web Simulator](https://help.opengolfsim.com/web/webgl/)
- [Developer API](https://help.opengolfsim.com/desktop/apis/)
- [Shot Data API](https://help.opengolfsim.com/desktop/apis/shot-data/)
