# rpiPan Wiring Diagram

## Full 29-Pad Tenor Pan (mux_scan mode)

The default configuration uses:

- **Waveshare Pico-Audio** HAT for I2S audio output (PCM5101A DAC)
- **ADS1115** I2C ADC for reading the mux analog signals
- **2x HW-178** (CD74HC4067) analog multiplexer modules for 29 FSR pads

Since the Pico-Audio HAT occupies GP26/GP27/GP28 (the Pico's only ADC pins)
for I2S, an external ADS1115 I2C ADC reads the mux analog outputs instead.
This gives 16-bit resolution at up to 860 samples/second.

### Components

| Component | Description |
|-----------|-------------|
| Raspberry Pi Pico / Pico 2 | Main controller |
| Waveshare Pico-Audio | I2S DAC HAT (PCM5101A), plugs onto Pico |
| ADS1115 | 16-bit I2C ADC breakout (4 channels) |
| 2x HW-178 | CD74HC4067 16-channel analog mux breakout |
| 29x FSR | Force Sensitive Resistors (one per pad) |
| 29x 10K resistor | Voltage dividers for FSR pads |
| 4W speaker (4-8 ohm) | Connects to Pico-Audio 3.5mm or speaker header |

The HW-178 is a common breakout board (17x40mm) with a 1x8 header
(SIG, S0-S3, EN, VCC, GND) and a 1x16 header (C0-C15). It operates at
2-6V, so it works directly with the Pico's 3.3V logic. The EN pin has an
internal pull-down (enabled by default) — our wiring drives EN explicitly
to switch between the two muxes.

### Pico Pin Allocation

| Pin | Function | Description |
|-----|----------|-------------|
| GP4 | I2C SDA | ADS1115 data |
| GP5 | I2C SCL | ADS1115 clock |
| GP10 | S0 (output) | Mux select bit 0 (shared) |
| GP11 | S1 (output) | Mux select bit 1 (shared) |
| GP12 | S2 (output) | Mux select bit 2 (shared) |
| GP13 | S3 (output) | Mux select bit 3 (shared) |
| GP14 | EN_A (output) | Mux A enable (active low) |
| GP15 | EN_B (output) | Mux B enable (active low) |
| GP26 | I2S DATA | Pico-Audio DIN (via HAT) |
| GP27 | I2S BCK | Pico-Audio bit clock (via HAT) |
| GP28 | I2S LRCK | Pico-Audio word clock (via HAT) |
| GP25 | LED | Onboard LED (activity) |

**12 pins used, 14 free** for future expansion.

The Pico-Audio HAT plugs directly onto the Pico headers — no wiring
needed for audio. Power (3.3V, 5V, GND) is supplied through the HAT
headers too.

### Main Wiring

```
                     Raspberry Pi Pico
                 ┌─────────────────────────┐
                 │                         │
           3.3V ─┤3V3              GP26    ├─┐
                 │                 GP27    ├─┤── Pico-Audio HAT
            GND ─┤GND              GP28    ├─┤   (plugs directly
                 │                 3V3     ├─┤    onto Pico headers)
                 │                 GND     ├─┘
                 │  MUX SELECT (shared)    │
                 │                         │
         S0 ◄── ┤GP10                     │
         S1 ◄── ┤GP11                     │
         S2 ◄── ┤GP12                     │
         S3 ◄── ┤GP13                     │
                 │                         │
      EN_A ◄── ┤GP14                     │
      EN_B ◄── ┤GP15                     │
                 │                         │
     I2C SDA ── ┤GP4                      │
     I2C SCL ── ┤GP5                      │
                 │                         │
                 └─────────────────────────┘


    ┌──────────────────────┐
    │  ADS1115  (I2C ADC)  │
    │                      │
    │  VCC ── 3.3V         │
    │  GND ── GND          │
    │  SDA ── GP4          │
    │  SCL ── GP5          │
    │  ADDR ── GND (0x48)  │
    │                      │
    │  A0  ── Mux A SIG    │
    │  A1  ── Mux B SIG    │
    │  A2  ── (free)       │
    │  A3  ── (free)       │
    └──────────────────────┘


    ┌─────────────────────────────┐  ┌─────────────────────────────┐
    │   MUX A  (HW-178)           │  │   MUX B  (HW-178)           │
    │                             │  │                             │
    │  VCC ── 3.3V                │  │  VCC ── 3.3V                │
    │  GND ── GND                 │  │  GND ── GND                 │
    │  EN  ── GP14                │  │  EN  ── GP15                │
    │  SIG ── ADS1115 A0          │  │  SIG ── ADS1115 A1          │
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

### Audio Output (Waveshare Pico-Audio HAT)

The Pico-Audio HAT plugs directly onto the Pico. It contains a PCM5101A
I2S DAC and APA2068 amplifier. Audio is output via:

- **3.5mm headphone jack** (line level)
- **Speaker header** (amplified, for 4W / 4-8 ohm speaker)

No external amplifier, RC filter, or additional wiring is needed for
audio — the HAT handles everything. Volume is controlled in software
via velocity.

The I2S connection uses 3 pins (fixed by the HAT PCB):

| I2S Signal | Pico Pin | Pico-Audio Pin |
|------------|----------|----------------|
| DATA | GP26 | DIN |
| BCK (bit clock) | GP27 | BCK |
| LRCK (word clock) | GP28 | LRCK |

**Note:** The Pico-Audio Rev2.1 (CS4344) uses different pin assignments.
If you have the Rev2.1, update the `"i2s"` section in `pan_layout.json`.

## Alternative: PWM Audio (no I2S HAT)

If you don't have a Pico-Audio HAT, you can use PWM audio output instead.
This frees up GP26/GP27/GP28 for native ADC, so no ADS1115 is needed.

Change `pan_layout.json`:

```json
"audio_out": "pwm",
"audio_pin": "GP18",
"mux": {
  "mux_a": {"analog_pin": "GP26", "enable_pin": "GP14"},
  "mux_b": {"analog_pin": "GP27", "enable_pin": "GP15"},
  ...
}
```

Remove the `"adc"` and `"i2s"` sections. PWM audio needs an external
amplifier (e.g. PAM8403) with an RC filter:

```
                PAM8403 module
GP18 ─── [1K] ───┬─── L-IN ┌──────────┐
                  │         │ PAM8403  │──── Speaker + (4W, 4-8 ohm)
               [100nF]      │          │──── Speaker -
                  │    GND ─┤ GND      │
                 GND   5V ──┤ VCC      │  ← power from USB or battery
                            └──────────┘
```

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

| Board | I2C pins | GPIO pins | I2S / Audio |
|-------|----------|-----------|-------------|
| Pico / Pico 2 | GP4/GP5 (I2C0) | GP0-GP22 | GP26-28 (I2S) or any (PWM) |
| Pico W | GP4/GP5 (I2C0) | GP0-GP22 | GP26-28 (I2S) or any (PWM) |
| ESP32-S3 | IO8/IO9 | IO0-IO48 | Any IO pins |
| Arduino Nano RP2040 | A4/A5 | D0-D13 | Any D pin |

## Tuning

- **10K resistor**: Adjust to match your FSR's range. Larger = more
  sensitivity to light touches. Start with 10K.
- **threshold** (default 3000): ADC value that triggers a note. Lower =
  more sensitive. Range 0-65535. ~3000 ≈ 0.15V.
- **settle_us** (default 100): Microseconds to wait after switching mux
  channel. Increase if readings are noisy or crosstalk between channels.
- **Velocity curve**: `(vel/127)^0.7` in the player. The linear ADC-to-velocity
  mapping combined with this power curve gives natural-feeling dynamics.
- **ADS1115 data rate**: Set to 860 SPS (maximum) by default. Full 29-pad
  scan takes ~35ms at this rate (~28 Hz). Sufficient for steel pan input.
