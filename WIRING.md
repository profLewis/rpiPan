# rpiPan Wiring Diagram

## Full 29-Pad Tenor Pan (mux_scan mode)

The `mux_scan` mode uses **2x CD74HC4067** analog multiplexers to scan all
29 pads through just 9 Pico GPIO pins. Each pad has an FSR (Force Sensitive
Resistor) in a voltage divider. The analog reading provides both touch
detection (threshold crossing) and velocity (signal magnitude).

### Pico Pin Allocation

| Pin | Function | Description |
|-----|----------|-------------|
| GP10 | S0 (output) | Mux select bit 0 (shared) |
| GP11 | S1 (output) | Mux select bit 1 (shared) |
| GP12 | S2 (output) | Mux select bit 2 (shared) |
| GP13 | S3 (output) | Mux select bit 3 (shared) |
| GP14 | EN_A (output) | Mux A enable (active low) |
| GP15 | EN_B (output) | Mux B enable (active low) |
| GP26 | ADC0 (input) | Mux A signal (analog) |
| GP27 | ADC1 (input) | Mux B signal (analog) |
| GP18 | Audio (output) | PWM audio to speaker/amp |
| GP25 | LED | Onboard LED (activity) |

**10 pins used, 16 free** for future expansion.

### Main Wiring

```
                       Raspberry Pi Pico
                   ┌─────────────────────────┐
                   │                         │
             3.3V ─┤3V3                  GP18├──[1K]──┬── Amp/Speaker (+)
                   │                         │        │
              GND ─┤GND                  GND ├────┐ [100nF]
                   │                         │    │   │
                   │  MUX SELECT (shared)    │    │  GND
                   │                         │    │
           S0 ◄── ┤GP10             GP26/ADC0├────┼── Mux A SIG
           S1 ◄── ┤GP11             GP27/ADC1├────┼── Mux B SIG
           S2 ◄── ┤GP12                     │    │
           S3 ◄── ┤GP13                     │    │
                   │                         │    │
        EN_A ◄── ┤GP14                     │    │
        EN_B ◄── ┤GP15                     │    │
                   │                         │    │
                   │                  3V3    ├──┐ │
                   │                  GND    ├──┼─┘
                   └─────────────────────────┘  │
                                                │
          ┌─────────────────────────────────────┘
          │
        3.3V


    ┌─────────────────────────────┐  ┌─────────────────────────────┐
    │   MUX A  (CD74HC4067)       │  │   MUX B  (CD74HC4067)       │
    │                             │  │                             │
    │  VCC ── 3.3V                │  │  VCC ── 3.3V                │
    │  GND ── GND                 │  │  GND ── GND                 │
    │  EN  ── GP14                │  │  EN  ── GP15                │
    │  SIG ── GP26 (ADC0)         │  │  SIG ── GP27 (ADC1)         │
    │  S0  ── GP10 ──────────┐    │  │  S0  ── GP10 ──────────┐    │
    │  S1  ── GP11 ──────────┤    │  │  S1  ── GP11 ──────────┤    │
    │  S2  ── GP12 ──────────┤    │  │  S2  ── GP12 ──────────┤    │
    │  S3  ── GP13 ───(shared)    │  │  S3  ── GP13 ───(shared)    │
    │                             │  │                             │
    │  C0  ── Pad: C4   (outer)   │  │  C0  ── Pad: E5  (central) │
    │  C1  ── Pad: C#4  (outer)   │  │  C1  ── Pad: F5  (central) │
    │  C2  ── Pad: D4   (outer)   │  │  C2  ── Pad: F#5 (central) │
    │  C3  ── Pad: Eb4  (outer)   │  │  C3  ── Pad: G5  (central) │
    │  C4  ── Pad: E4   (outer)   │  │  C4  ── Pad: Ab5 (central) │
    │  C5  ── Pad: F4   (outer)   │  │  C5  ── Pad: A5  (central) │
    │  C6  ── Pad: F#4  (outer)   │  │  C6  ── Pad: Bb5 (central) │
    │  C7  ── Pad: G4   (outer)   │  │  C7  ── Pad: B5  (central) │
    │  C8  ── Pad: Ab4  (outer)   │  │  C8  ── Pad: C6  (inner)   │
    │  C9  ── Pad: A4   (outer)   │  │  C9  ── Pad: C#6 (inner)   │
    │  C10 ── Pad: Bb4  (outer)   │  │  C10 ── Pad: D6  (inner)   │
    │  C11 ── Pad: B4   (outer)   │  │  C11 ── Pad: Eb6 (inner)   │
    │  C12 ── Pad: C5  (central)  │  │  C12 ── Pad: E6  (inner)   │
    │  C13 ── Pad: C#5 (central)  │  │  C13 ── (unused)           │
    │  C14 ── Pad: D5  (central)  │  │  C14 ── (unused)           │
    │  C15 ── Pad: Eb5 (central)  │  │  C15 ── (unused)           │
    └─────────────────────────────┘  └─────────────────────────────┘
```

### Per-Pad Wiring (FSR Voltage Divider)

Each pad has an FSR in a voltage divider. The output connects to a mux
channel input (C0-C15). No separate digital pin needed.

```
        3.3V
         │
        [FSR]  ← force from strike
         │
         ├──── [10K] ──── GND
         │
         └──── Mux Channel (C0, C1, etc.)

    No force:   FSR high resistance  → ~0V    → below threshold
    Light tap:  FSR medium resistance → ~1V   → velocity ~30
    Hard hit:   FSR low resistance   → ~2.5V  → velocity ~110
```

### Complete Pad Assignment Table

| # | Note | Ring | Mux | Channel | MIDI |
|---|------|------|-----|---------|------|
| 0 | C4 | outer | A | 0 | 60 |
| 1 | C#4 | outer | A | 1 | 61 |
| 2 | D4 | outer | A | 2 | 62 |
| 3 | Eb4 | outer | A | 3 | 63 |
| 4 | E4 | outer | A | 4 | 64 |
| 5 | F4 | outer | A | 5 | 65 |
| 6 | F#4 | outer | A | 6 | 66 |
| 7 | G4 | outer | A | 7 | 67 |
| 8 | Ab4 | outer | A | 8 | 68 |
| 9 | A4 | outer | A | 9 | 69 |
| 10 | Bb4 | outer | A | 10 | 70 |
| 11 | B4 | outer | A | 11 | 71 |
| 12 | C5 | central | A | 12 | 72 |
| 13 | C#5 | central | A | 13 | 73 |
| 14 | D5 | central | A | 14 | 74 |
| 15 | Eb5 | central | A | 15 | 75 |
| 16 | E5 | central | B | 0 | 76 |
| 17 | F5 | central | B | 1 | 77 |
| 18 | F#5 | central | B | 2 | 78 |
| 19 | G5 | central | B | 3 | 79 |
| 20 | Ab5 | central | B | 4 | 80 |
| 21 | A5 | central | B | 5 | 81 |
| 22 | Bb5 | central | B | 6 | 82 |
| 23 | B5 | central | B | 7 | 83 |
| 24 | C6 | inner | B | 8 | 84 |
| 25 | C#6 | inner | B | 9 | 85 |
| 26 | D6 | inner | B | 10 | 86 |
| 27 | Eb6 | inner | B | 11 | 87 |
| 28 | E6 | inner | B | 12 | 88 |

### Audio Output (4W speaker via amplifier)

**Do not drive a speaker directly from the Pico GPIO** — the GPIO can only
source ~12mA at 3.3V. Use a class-D amplifier module.

Recommended: **PAM8403** (2x3W stereo, ~$1) or **MAX98357A** (3W mono I2S).
For a 4W / 4-8 ohm speaker, the PAM8403 is ideal:

```
                PAM8403 module
GP18 ─── [1K] ───┬─── L-IN ┌──────────┐
                  │         │ PAM8403  │──── Speaker + (4W, 4-8Ω)
               [100nF]      │          │──── Speaker -
                  │    GND ─┤ GND      │
                 GND   5V ──┤ VCC      │  ← power from USB or battery
                            └──────────┘

    RC filter (1K + 100nF): smooths PWM before amplifier input
    PAM8403 VCC: 5V from Pico VBUS pin (USB power) or external supply
    Volume: controlled by velocity in software (no pot needed)
```

The RC low-pass filter (1K + 100nF, ~1.6 kHz cutoff) removes the PWM
carrier frequency. The PAM8403 amplifies the filtered audio signal to
drive the 4W speaker.

## Simpler Configurations

### mux_touch mode (fewer pads + digital trigger)

For fewer pads where you have enough GPIO pins for individual digital
triggers (up to ~20 pads), use `mux_touch` mode with a single mux:

```json
"input_mode": "mux_touch",
"mux": {"analog_pin": "GP26", "select_pins": ["GP10","GP11","GP12","GP13"]},
"pins": {"GP0": {"note": "C4", "mux_channel": 0}}
```

### button mode (no analog, simplest wiring)

For testing or simple setups with a few buttons:

```json
"input_mode": "button",
"pins": {"GP0": "C4", "GP1": "D4", "GP2": "E4"}
```

Each button connects between the GPIO pin and GND (internal pull-up used).

## Board Compatibility

The pin names in `pan_layout.json` are board-agnostic — they reference
whatever names CircuitPython's `board` module provides. Change the pin
names to match your board:

| Board | ADC pins | GPIO pins | Audio |
|-------|----------|-----------|-------|
| Pico / Pico 2 | GP26, GP27, GP28 | GP0-GP22 | Any GP pin |
| Pico W | GP26, GP27, GP28 | GP0-GP22 | Any GP pin |
| ESP32-S3 | IO1-IO10 | IO0-IO48 | Any IO pin |
| Arduino Nano RP2040 | A0-A3 | D0-D13 | Any D pin |

## Tuning

- **10K resistor**: Adjust to match your FSR's range. Larger = more
  sensitivity to light touches. Start with 10K.
- **threshold** (default 3000): ADC value that triggers a note. Lower =
  more sensitive. Range 0-65535. ~3000 ≈ 0.15V.
- **settle_us** (default 100): Microseconds to wait after switching mux
  channel. Increase if readings are noisy or crosstalk between channels.
- **Velocity curve**: `(vel/127)^0.7` in the player. The linear ADC-to-velocity
  mapping combined with this power curve gives natural-feeling dynamics.
