# Sound Trigger Wiring Guide

Step-by-step instructions for wiring the sound trigger that enables spin detection in rolling buffer mode.

> **Parts needed:** See the [Parts List](PARTS.md#sound-trigger-for-rolling-buffer-mode) for what to buy.

## Overview

The SparkFun SEN-14262 sound detector listens for club impact and triggers the OPS243-A radar to dump its I/Q buffer. That captured data is then analyzed for spin rate estimation.

The setup uses one USB data cable plus four jumper connections:

```
OPS243-A micro-USB → Raspberry Pi USB-A (radar power and data)
SEN-14262 GATE → OPS243-A HOST_INT (J3 Pin 3)
SEN-14262 VCC  → Raspberry Pi 3.3V
SEN-14262 GND  → Raspberry Pi GND (shared with OPS243-A GND)
OPS243-A GND   → Raspberry Pi GND (J3 Pin 10; shared ground)
```

Leave OPS243-A J3 pin 9 (5V) disconnected because USB powers the radar.

## Before You Wire: Solder R17

The SEN-14262 is designed for 5V but runs at 3.3V in this setup. At 3.3V the preamp gain is too high and the GATE output can get stuck high. To fix this, solder a through-hole resistor into the **R17** position on the SEN-14262 board.

R17 sits in parallel with the onboard 100kΩ surface-mount R3, reducing the preamp gain:

| R17 Value | Effective Resistance | Gain Reduction |
|-----------|---------------------|----------------|
| 47kΩ | ~32kΩ | Moderate — try this first |
| 33kΩ | ~25kΩ | More aggressive — for noisy environments |

Start with 47kΩ. If the GATE LED still stays lit without sound, switch to a lower value.

---

## Wiring

### Step 1: Identify OPS243-A J3 Header Pins

```
Component/antenna side facing you, antennas at the top and micro-USB at
the lower-right:

far left                                      nearest USB
┌──────┬────┬───┬───┬───┬───┬───┬──────────┬───┬───────┐
│10 GND│9 5V│ 8 │ 7 │ 6 │ 5 │ 4 │3 HOST_INT│ 2 │1 GPIO │
└──────┴────┴───┴───┴───┴───┴───┴──────────┴───┴───────┘
```

- **Pin 10** = GND
- **Pin 9** = 5V; leave disconnected when the radar is USB-powered
- **Pin 3** = HOST_INT (3.3V trigger input in rolling-buffer mode)
- **Pin 1** = GPIO; it is not ground

In this orientation, J3 pin 3 is third from the right and J3 pin 10 is at the far left. This pin assignment follows OmniPreSense's [OPS243 datasheet](https://omnipresense.com/wp-content/uploads/2019/03/OPS-DS-003-0.1_OPS243.pdf) and [AN-027 rolling-buffer guide](https://omnipresense.com/wp-content/uploads/2025/06/AN-027-A_Rolling-Buffer.pdf).

### Step 2: Connect Power

1. Connect **SEN-14262 VCC** → **Pi 3.3V** (physical pin 1)
2. Connect **SEN-14262 GND** → **Pi GND** (physical pin 6)
3. Connect **OPS243-A GND (J3 Pin 10)** → same **Pi GND** rail

All three boards must share a common ground.

### Step 3: Connect Trigger

1. Connect **SEN-14262 GATE** → **OPS243-A HOST_INT (J3 Pin 3)**

That's it. No level shifter, no MOSFETs, no breadboard needed.

```
SEN-14262               Raspberry Pi           OPS243-A
┌───────────┐          ┌──────────┐          ┌──────────┐
│ VCC ──────┼──────────┤ 3.3V     │          │          │
│           │          │          │          │          │
│ GATE ─────┼──────────┼──────────┼──────────┤ HOST_INT │
│           │          │          │          │ (J3 P3)  │
│ GND ──────┼──────────┤ GND      ├──────────┤ GND      │
│           │          │          │          │ (J3 P10) │
└───────────┘          └──────────┘          └──────────┘
```

---

## Wiring Checklist

- [ ] R17 resistor soldered on SEN-14262 board
- [ ] SEN-14262 VCC → Pi 3.3V (pin 1)
- [ ] SEN-14262 GND → Pi GND (pin 6)
- [ ] SEN-14262 GATE → OPS243-A HOST_INT (J3 Pin 3)
- [ ] OPS243-A micro-USB → Pi USB-A using a data-capable cable
- [ ] OPS243-A GND (J3 Pin 10) → Pi GND (shared ground)
- [ ] OPS243-A J3 Pin 9 (5V) left disconnected

---

## One-Time Radar Setup

The OPS243-A must have rolling buffer mode saved to persistent memory for HOST_INT triggers to work. This is due to a firmware bug where the HOST_INT pin mode changes when transitioning modes at runtime.

```bash
# Configure and save rolling buffer mode to flash (one-time)
uv run python scripts/hardware-test/test_rolling_buffer_persist.py --setup

# Power cycle the radar (unplug USB, wait 3s, replug)

# Verify
uv run python scripts/hardware-test/test_rolling_buffer_persist.py --test
```

---

## Testing

### Quick Test: Visual

Make a loud sound near the SEN-14262. The onboard LED should flash briefly, then turn off. If the LED stays on constantly, you need a lower-value resistor in R17.

### Full Test: Software

```bash
uv run python scripts/hardware-test/test_sound_trigger_hardware.py
```

You should see:
```
Ready for hardware sound triggers!
Make a sound near the sensor... (Ctrl+C to quit)

[1] Waiting for hardware trigger (timeout=60s)...
  TRIGGER RECEIVED after 0.02s!
  I/Q samples: 4096 I, 4096 Q
```

---

## Troubleshooting

### GATE LED stays on (stuck high)

The preamp gain is too high for 3.3V operation.
- **Fix:** Solder a lower-value resistor into R17 (try 33kΩ instead of 47kΩ)

### No trigger received

1. Check the GATE LED flashes when you clap
2. Verify GND is shared between all three boards (Pi, SEN-14262, OPS243-A)
3. Verify HOST_INT is J3 **Pin 3**, third from the right in the orientation shown above
4. Verify the OPS243-A ground wire is on J3 **Pin 10**, not pin 1
5. Run `uv run python scripts/hardware-test/test_rolling_buffer_persist.py --test` to confirm radar is in rolling buffer mode

### Triggers constantly / too sensitive

- Use a lower-value R17 resistor to reduce gain
- Move the sensor further from the hitting area

### Triggers but no I/Q data

- Run the one-time radar setup (see above) — HOST_INT mode must be saved to flash
- Power cycle the radar after setup
