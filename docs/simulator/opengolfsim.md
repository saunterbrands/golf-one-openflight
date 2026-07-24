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

1. Golf One boots into its Live dashboard.
2. Open **Settings**, choose **OpenGolfSim Simulator**, and press **Show selected
   display**.
3. Golf One checks whether `https://app.opengolfsim.com/account/simulator` is
   reachable. When online it opens the official hosted simulator; when offline
   it opens the appliance-local FUSE Practice Range.
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
- applies a commit- and context-guarded patch that selects FUSE's explicit
  WebGL renderer for the Practice Range;
- builds only the Practice Range;
- copies its static runtime and required license into
  `~/.local/share/golf-one/fuse`;
- writes the optimized build to its own commit-and-variant directory instead
  of overwriting an existing runtime;
- keeps all third-party FUSE code and assets outside this Git repository.

The explicit WebGL variant avoids the extra WebGPU-wrapper path when Chromium
ultimately uses a WebGL backend on the supported ARM appliances. On a
Raspberry Pi 5, the installer also selects the measured `pi-balanced` profile:
the two large repeating grass textures are capped at 4x anisotropic filtering
while native 1920 x 720 resolution, 4x MSAA, scene geometry, shadows, and shot
physics remain unchanged. On other boards, including Orange Pi 5, `auto` keeps
the full 16x texture setting. Installation fails closed if the checked-out
commit or the expected upstream source context does not match.

The Pi profile raised the repeated fixed-shot average from 15.42 FPS to 21.73
FPS (+41%) on the Waveshare display. A more aggressive 33 FPS experiment also
disabled MSAA, but it was rejected because the ball trace and mountain edges
were visibly jagged.

### Orange Pi 5 rendering default

The Orange Pi GNOME/X11 launcher pins Chromium to the measured Mali-G610 fast
path:

```text
--ozone-platform=x11
--use-angle=gles
--enable-gpu-rasterization
--force-device-scale-factor=1
```

Chromium reports `ANGLE (Mesa, Mali-G610 (Panfrost), OpenGL ES 3.1)` and the
GPU process owns the Panthor DRM render node. The local full-quality explicit
WebGL range measured 59.83 FPS at 1920 x 720, effectively the 60 Hz display
ceiling. The equivalent upstream renderer averaged 42.67 FPS in the same clean
GNOME/X11 session.

A compositor-free Openbox session was also tested rather than assumed faster.
Its first two upstream-renderer shots averaged 43.73 FPS, but a longer four-shot
repeat fell to 39.22 FPS and its explicit-WebGL average was marginally below
GNOME. Openbox is therefore not the boot default. Keeping GNOME preserves the
normal desktop recovery path while matching or beating the lightweight session
in the repeated rendering test.

The GPU remains on its adaptive `simple_ondemand` governor. It reached the full
1 GHz clock during the benchmark, so fixing the governor at `performance` would
add idle power and heat without exposing a higher rendering clock.

For a controlled rendering A/B, override either pin only for that launch:

```bash
GOLF_ONE_OZONE_PLATFORM=auto \
GOLF_ONE_FORCE_DEVICE_SCALE_FACTOR=1 \
scripts/launch-golf-one-gnome.sh
```

Override automatic board detection when building a runtime with:

```bash
GOLF_ONE_FUSE_PROFILE=full scripts/setup/install-offline-fuse-range.sh
GOLF_ONE_FUSE_PROFILE=pi-balanced scripts/setup/install-offline-fuse-range.sh
```

When the installer replaces an active runtime, it keeps that runtime's version
directory untouched and points `~/.local/share/golf-one/fuse/previous` to it.
To roll back, repoint `current` and restart Golf One:

```bash
FUSE_ROOT="$HOME/.local/share/golf-one/fuse"
ln -sfn "$(readlink "$FUSE_ROOT/previous")" "$FUSE_ROOT/current"
```

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

1. From the Golf One Dashboard, open **Settings**, choose **OpenGolfSim
   Simulator**, and press **Show selected display**.
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
