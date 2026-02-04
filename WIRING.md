# rpiPan Wiring Guide

Four hardware configurations are supported. All use the [Waveshare
Pico-Audio HAT](https://www.waveshare.com/wiki/Pico-Audio)
([buy](https://thepihut.com/products/pico-audio-audio-module-for-raspberry-pi-pico-inc-speakers))
for I2S audio output unless noted otherwise.

Code design and testing: P. Lewis

## Audio Output (all configurations)

The [Waveshare Pico-Audio HAT](https://www.waveshare.com/wiki/Pico-Audio)
plugs directly onto the Pico headers. It contains a PCM5101A I2S DAC and
APA2068 amplifier. Audio is output via:

- **Included speakers** — connect to the speaker header on the HAT
- **3.5mm headphone jack** — line level output

No external amplifier, RC filter, or additional wiring is needed — the
HAT handles everything. Volume is controlled in software via velocity.

The I2S connection uses 3 pins (fixed by the HAT PCB):

| I2S Signal | Pico Pin | Pico-Audio Pin |
|------------|----------|----------------|
| DATA | GP26 | DIN |
| BCK (bit clock) | GP27 | BCK |
| LRCK (word clock) | GP28 | LRCK |

**Note:** The Pico-Audio Rev2.1 (CS4344) uses different pin assignments.
If you have the Rev2.1, update the `"i2s"` section in `pan_layout.json`.

---

## Configuration A: Full 29-Pad Tenor Pan (`mux_scan`)

The default configuration. Uses dual multiplexers to scan all 29 FSR pads
with only 9 GPIO pins. Velocity-sensitive via ADS1115 I2C ADC.

Since the Pico-Audio HAT occupies GP26/GP27/GP28 (the Pico's only ADC
pins) for I2S, an external ADS1115 I2C ADC reads the mux analog outputs
instead. This gives 16-bit resolution at up to 860 samples/second.

### Components

| Component | Description | Buy (UK) |
|-----------|-------------|----------|
| Raspberry Pi Pico H | Main controller ([pinout](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf)) | [The Pi Hut](https://thepihut.com/products/raspberry-pi-pico) / [Pimoroni](https://shop.pimoroni.com/products/raspberry-pi-pico) |
| Waveshare Pico-Audio HAT | I2S DAC (PCM5101A), plugs onto Pico ([wiki](https://www.waveshare.com/wiki/Pico-Audio)) | [The Pi Hut](https://thepihut.com/products/pico-audio-audio-module-for-raspberry-pi-pico-inc-speakers) |
| ADS1115 | 16-bit I2C ADC breakout, 4 channels ([datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf)) | [The Pi Hut](https://thepihut.com/products/adafruit-ads1115-16-bit-adc-4-channel-with-programmable-gain-amplifier) |
| 2x HW-178 | CD74HC4067 16-channel analog mux breakout | [Amazon UK](https://www.amazon.co.uk/CD74HC4067-16-Channel-Digital-Multiplexer-Breakout/dp/B06Y1L95GK) |
| 29x FSR | Force Sensitive Resistors (one per pad) | [The Pi Hut](https://thepihut.com/products/round-force-sensitive-resistor-fsr) |
| 29x 10K resistor | Voltage dividers for FSR pads | — |

The HW-178 is a common breakout board (17x40mm) with a 1x8 header
(SIG, S0-S3, EN, VCC, GND) and a 1x16 header (C0-C15). It operates at
2-6V, so it works directly with the Pico's 3.3V logic. The EN pin has an
internal pull-down (enabled by default) — our wiring drives EN explicitly
to switch between the two muxes.

### Pin Allocation

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

### Wiring Diagram

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

### pan_layout.json

```json
"input_mode": "mux_scan",
"audio_out": "i2s",
"i2s": {"bit_clock": "GP27", "word_select": "GP28", "data": "GP26"},
"adc": {"type": "i2c", "sda": "GP4", "scl": "GP5"},
"mux": {
  "select_pins": ["GP10", "GP11", "GP12", "GP13"],
  "mux_a": {"enable_pin": "GP14"},
  "mux_b": {"enable_pin": "GP15"},
  "threshold": 3000,
  "settle_us": 100
},
"pads": [
  {"note": "C4", "mux": "a", "channel": 0},
  {"note": "C#4", "mux": "a", "channel": 1},
  ...
]
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

---

## Configuration B: Direct Sensors via Grove Shield (`direct`)

Vibration sensors (SW-420), FSRs, or buttons connected directly to GPIO
pins — no multiplexer needed. Up to 15 sensors on free GPIO pins.
Optionally reads analog velocity from ADS1115 channels (up to 4 pads).

Code design and testing: P. Lewis

### Components

| Component | Description | Buy (UK) |
|-----------|-------------|----------|
| Raspberry Pi Pico H | Main controller ([pinout](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf)) | [The Pi Hut](https://thepihut.com/products/raspberry-pi-pico) / [Pimoroni](https://shop.pimoroni.com/products/raspberry-pi-pico) |
| Waveshare Pico-Audio HAT | I2S DAC (PCM5101A), plugs onto Pico ([wiki](https://www.waveshare.com/wiki/Pico-Audio)) | [The Pi Hut](https://thepihut.com/products/pico-audio-audio-module-for-raspberry-pi-pico-inc-speakers) |
| Seeed Grove Shield for Pi Pico | Easy-connect sensor breakout (optional) | [The Pi Hut](https://thepihut.com/products/grove-shield-for-raspberry-pi-pico-v1-0) |
| 7-15x SW-420 vibration sensor | Vibration switch modules. Or FSRs, piezo discs, buttons | [Amazon UK](https://www.amazon.co.uk/DollaTek-SW-420-Vibration-Sensor-Arduino/dp/B07DJ5NVSC) |
| ADS1115 | 16-bit I2C ADC (optional, for velocity on up to 4 pads) ([datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf)) | [The Pi Hut](https://thepihut.com/products/adafruit-ads1115-16-bit-adc-4-channel-with-programmable-gain-amplifier) |

### Pin Allocation

| Pin | Function | Description |
|-----|----------|-------------|
| GP4 | I2C SDA | ADS1115 data (if used) |
| GP5 | I2C SCL | ADS1115 clock (if used) |
| GP0-GP3 | Sensor input | Direct pad triggers |
| GP6-GP9 | Sensor input | Direct pad triggers |
| GP16-GP22 | Sensor input | Direct pad triggers (Grove connectors) |
| GP26 | I2S DATA | Pico-Audio DIN (via HAT) |
| GP27 | I2S BCK | Pico-Audio bit clock (via HAT) |
| GP28 | I2S LRCK | Pico-Audio word clock (via HAT) |
| GP25 | LED | Onboard LED (activity) |

**15 GPIO pins available** for sensor input.

### Wiring Diagram

```
                     Raspberry Pi Pico
                 ┌─────────────────────────┐
                 │                         │
           3.3V ─┤3V3              GP26    ├─┐
                 │                 GP27    ├─┤── Pico-Audio HAT
            GND ─┤GND              GP28    ├─┘   (I2S audio +
                 │                         │      included speakers)
                 │  SENSOR GPIO PINS       │
                 │                         │
       Sensor 1 ─┤GP16  (Grove D16)       │
       Sensor 2 ─┤GP17  (Grove D16)       │
       Sensor 3 ─┤GP18  (Grove D18)       │
       Sensor 4 ─┤GP19  (Grove D18)       │
       Sensor 5 ─┤GP20  (Grove D20)       │
       Sensor 6 ─┤GP21  (Grove D20)       │
       Sensor 7 ─┤GP6   (Grove I2C1)      │
       Sensor 8 ─┤GP7   (Grove I2C1)      │
                 │  (more: GP0-3, GP8-9,   │
                 │   GP22 also available)   │
                 │                         │
       I2C SDA ──┤GP4                      │
       I2C SCL ──┤GP5                      │
                 │                         │
                 └─────────────────────────┘


    ┌───────────────────────────────────────┐
    │  ADS1115  (I2C ADC, optional)         │
    │                                       │
    │  VCC ── 3.3V    SDA ── GP4            │
    │  GND ── GND     SCL ── GP5            │
    │  ADDR ── GND (0x48)                   │
    │                                       │
    │  A0  ── Sensor 1 analog (velocity)    │
    │  A1  ── Sensor 2 analog (velocity)    │
    │  A2  ── Sensor 3 analog (velocity)    │
    │  A3  ── Sensor 4 analog (velocity)    │
    └───────────────────────────────────────┘


    ┌──────────────────────────────────┐
    │  SW-420 Vibration Sensor         │
    │                                  │
    │  VCC ── 3.3V                     │
    │  GND ── GND                      │
    │  DO  ── GPIO pin (e.g. GP16)     │
    │                                  │
    │  Output: HIGH when stable        │
    │          LOW  when vibration      │
    │  Sensitivity: adjust via pot     │
    └──────────────────────────────────┘
```

The SW-420 vibration sensor has a digital output only (no analog). For
velocity-sensitive pads, use a raw piezo element or FSR with a voltage
divider connected to an ADS1115 channel alongside the digital trigger.

### Grove Shield Connector Map

| Pin | Grove Connector | Notes |
|-----|----------------|-------|
| GP0 | UART0 TX | Available if UART not used |
| GP1 | UART0 RX | Available if UART not used |
| GP2 | — | Free |
| GP3 | — | Free |
| GP6 | I2C1 SDA | Available for digital input |
| GP7 | I2C1 SCL | Available for digital input |
| GP8 | I2C0 SDA | Available for digital input |
| GP9 | I2C0 SCL | Available for digital input |
| GP16 | Digital D16 | Grove digital connector |
| GP17 | Digital D16 | Grove digital connector |
| GP18 | Digital D18 | Grove digital connector |
| GP19 | Digital D18 | Grove digital connector |
| GP20 | Digital D20 | Grove digital connector |
| GP21 | Digital D20 | Grove digital connector |
| GP22 | — | Free |

### pan_layout.json

```json
"input_mode": "direct",
"adc": {"type": "i2c", "sda": "GP4", "scl": "GP5"},
"pads": [
  {"note": "C4",  "pin": "GP16", "adc_channel": 0},
  {"note": "D4",  "pin": "GP17", "adc_channel": 1},
  {"note": "E4",  "pin": "GP18", "adc_channel": 2},
  {"note": "F4",  "pin": "GP19", "adc_channel": 3},
  {"note": "G4",  "pin": "GP20"},
  {"note": "A4",  "pin": "GP21"},
  {"note": "B4",  "pin": "GP6"},
  {"note": "C5",  "pin": "GP7"}
]
```

Each pad has:
- `"note"` — note identifier (e.g. "C4", "F#5")
- `"pin"` — GPIO pin for digital trigger (active low, internal pull-up)
- `"adc_channel"` (optional) — ADS1115 channel 0-3 for analog velocity

---

## Configuration C: Mux Touch (`mux_touch`)

Fewer pads with individual digital trigger pins plus a single mux for
analog velocity reading. Up to ~20 pads.

### Components

| Component | Description | Buy (UK) |
|-----------|-------------|----------|
| Raspberry Pi Pico H | Main controller ([pinout](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf)) | [The Pi Hut](https://thepihut.com/products/raspberry-pi-pico) |
| Waveshare Pico-Audio HAT | I2S DAC (PCM5101A), plugs onto Pico ([wiki](https://www.waveshare.com/wiki/Pico-Audio)) | [The Pi Hut](https://thepihut.com/products/pico-audio-audio-module-for-raspberry-pi-pico-inc-speakers) |
| 1x HW-178 | CD74HC4067 16-channel analog mux breakout | [Amazon UK](https://www.amazon.co.uk/CD74HC4067-16-Channel-Digital-Multiplexer-Breakout/dp/B06Y1L95GK) |
| ADS1115 | 16-bit I2C ADC breakout (optional) ([datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf)) | [The Pi Hut](https://thepihut.com/products/adafruit-ads1115-16-bit-adc-4-channel-with-programmable-gain-amplifier) |
| FSR or piezo pads | One per note | [The Pi Hut](https://thepihut.com/products/round-force-sensitive-resistor-fsr) |

### Wiring Diagram

```
                     Raspberry Pi Pico
                 ┌─────────────────────────┐
                 │                         │
           3.3V ─┤3V3              GP26    ├─┐
                 │                 GP27    ├─┤── Pico-Audio HAT
            GND ─┤GND              GP28    ├─┘   (I2S audio +
                 │                         │      included speakers)
                 │  DIGITAL TRIGGER PINS   │
                 │                         │
         Pad 1 ─┤GP0                      │
         Pad 2 ─┤GP1                      │
         Pad 3 ─┤GP2                      │
         Pad 4 ─┤GP3                      │
           ...   │ (one GPIO per pad)      │
                 │                         │
                 │  MUX SELECT             │
         S0 ◄── ┤GP10                     │
         S1 ◄── ┤GP11                     │
         S2 ◄── ┤GP12                     │
         S3 ◄── ┤GP13                     │
                 │                         │
       I2C SDA ──┤GP4                      │
       I2C SCL ──┤GP5                      │
                 │                         │
                 └─────────────────────────┘


    ┌──────────────────────┐        ┌──────────────────────────┐
    │  ADS1115  (I2C ADC)  │        │  MUX  (HW-178)           │
    │                      │        │                          │
    │  VCC ── 3.3V         │        │  VCC ── 3.3V             │
    │  GND ── GND          │        │  GND ── GND              │
    │  SDA ── GP4          │        │  EN  ── GND (always on)  │
    │  SCL ── GP5          │        │  SIG ── ADS1115 A0       │
    │  ADDR ── GND (0x48)  │        │  S0  ── GP10             │
    │                      │        │  S1  ── GP11             │
    │  A0  ── Mux SIG      │        │  S2  ── GP12             │
    │                      │        │  S3  ── GP13             │
    └──────────────────────┘        │                          │
                                    │  C0  ── Pad 1 (analog)   │
                                    │  C1  ── Pad 2 (analog)   │
                                    │  ...                     │
                                    └──────────────────────────┘
```

### pan_layout.json

```json
"input_mode": "mux_touch",
"adc": {"type": "i2c", "sda": "GP4", "scl": "GP5"},
"mux": {
  "select_pins": ["GP10", "GP11", "GP12", "GP13"]
},
"pins": {
  "GP0": {"note": "C4", "mux_channel": 0},
  "GP1": {"note": "D4", "mux_channel": 1},
  "GP2": {"note": "E4", "mux_channel": 2}
}
```

---

## Configuration D: Buttons Only (`button`)

Simplest wiring — each pad is a switch or button to GND. No analog,
no mux, fixed velocity. Good for quick testing.

### Components

| Component | Description | Buy (UK) |
|-----------|-------------|----------|
| Raspberry Pi Pico H | Main controller ([pinout](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf)) | [The Pi Hut](https://thepihut.com/products/raspberry-pi-pico) |
| Waveshare Pico-Audio HAT | I2S DAC (PCM5101A), plugs onto Pico ([wiki](https://www.waveshare.com/wiki/Pico-Audio)) | [The Pi Hut](https://thepihut.com/products/pico-audio-audio-module-for-raspberry-pi-pico-inc-speakers) |
| Tactile buttons or switches | One per note | — |

### Wiring Diagram

```
                     Raspberry Pi Pico
                 ┌─────────────────────────┐
                 │                         │
           3.3V ─┤3V3              GP26    ├─┐
                 │                 GP27    ├─┤── Pico-Audio HAT
            GND ─┤GND              GP28    ├─┘   (I2S audio +
                 │                         │      included speakers)
                 │  BUTTON PINS            │
                 │                         │
      Button 1 ─┤GP0                      │
      Button 2 ─┤GP1                      │
      Button 3 ─┤GP2                      │
      Button 4 ─┤GP3                      │
           ...   │                         │
                 └─────────────────────────┘

    Each button:
         GPIO pin ────[button]──── GND
    (internal pull-up used, active low)
```

### pan_layout.json

```json
"input_mode": "button",
"pins": {
  "GP0": "C4",
  "GP1": "D4",
  "GP2": "E4",
  "GP3": "F4"
}
```

---

## Configuration E: PWM Audio — No I2S HAT (`mux_scan` or `direct`)

If you don't have a Pico-Audio HAT, you can use PWM audio output instead.
This frees up GP26/GP27/GP28 for native ADC, so no ADS1115 is needed for
the mux configuration.

### Components

| Component | Description | Buy (UK) |
|-----------|-------------|----------|
| Raspberry Pi Pico H | Main controller ([pinout](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf)) | [The Pi Hut](https://thepihut.com/products/raspberry-pi-pico) |
| PAM8403 amplifier module | Class-D stereo amp (optional) | [Amazon UK](https://www.amazon.co.uk/DollaTek-amplifier-Amplifier-Dual-channel-Headphones/dp/B07DJWGQVY) |
| Speaker (4-8 ohm) | Any small speaker | — |
| 1K resistor + 100nF capacitor | RC filter for PWM output | — |

### Wiring Diagram

```
                     Raspberry Pi Pico
                 ┌─────────────────────────┐
                 │                         │
           3.3V ─┤3V3                      │
            GND ─┤GND                      │
                 │                         │
    PWM audio ──┤GP18 ─── [1K] ───┬───────│───── PAM8403 L-IN
                 │                [100nF]  │
                 │                  │      │
                 │                 GND     │
                 │                         │
    ADC (mux A) ┤GP26              │      │
    ADC (mux B) ┤GP27              │      │
                 │                         │
                 │  (remaining pins same   │
                 │   as Config A for mux,  │
                 │   or Config B for       │
                 │   direct sensors)       │
                 └─────────────────────────┘

                PAM8403 module
    L-IN ─────┌──────────┐
              │ PAM8403  │──── Speaker +
         GND ─┤ GND      │──── Speaker -
          5V ──┤ VCC      │  ← power from USB or battery
              └──────────┘
```

### pan_layout.json

```json
"audio_out": "pwm",
"audio_pin": "GP18"
```

Remove the `"i2s"` section. When using with mux_scan, also remove `"adc"`
and use native ADC via `"mux_a": {"analog_pin": "GP26"}`.

---

## Board Compatibility

All configurations work across these boards. The pin names in
`pan_layout.json` are board-agnostic — change them to match your board.

### Raspberry Pi Pico H / Pico 2

The primary target board. All configurations work as documented above.

- **Pico H**: [Buy (The Pi Hut)](https://thepihut.com/products/raspberry-pi-pico) / [Buy (Pimoroni)](https://shop.pimoroni.com/products/raspberry-pi-pico) — [Pinout (PDF)](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf) — [Interactive pinout](https://pico.pinout.xyz/) — [Datasheet](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf)
- **Pico 2**: [Buy (The Pi Hut)](https://thepihut.com/products/raspberry-pi-pico-2) / [Buy (Pimoroni)](https://shop.pimoroni.com/products/raspberry-pi-pico-2) — [Pinout (PDF)](https://datasheets.raspberrypi.com/pico/Pico-2-Pinout.pdf) — [Interactive pinout](https://pico2.pinout.xyz/) — [Datasheet](https://datasheets.raspberrypi.com/pico/pico-2-datasheet.pdf)

```
    Pico H / Pico 2 Pin Summary
    ┌───────────────────────────────┐
    │  GP0-GP22    General purpose  │
    │  GP25        Onboard LED      │
    │  GP26-GP28   ADC / I2S        │
    │  I2C0        GP4 (SDA), GP5 (SCL)  │
    │  I2C1        GP6 (SDA), GP7 (SCL)  │
    │  3V3, GND    Power            │
    └───────────────────────────────┘
```

### Raspberry Pi Pico W

Same as Pico H with the addition of WiFi. The onboard LED is controlled
via the WiFi chip (not GP25), but rpiPan handles this automatically.
All pin assignments are identical.

- **Pico W / WH**: [Buy (The Pi Hut)](https://thepihut.com/products/raspberry-pi-pico-w) / [Buy (Pimoroni)](https://shop.pimoroni.com/products/raspberry-pi-pico-w) — [Pinout (PDF)](https://datasheets.raspberrypi.com/picow/PicoW-A4-Pinout.pdf) — [Interactive pinout](https://picow.pinout.xyz/) — [Datasheet](https://datasheets.raspberrypi.com/picow/pico-w-datasheet.pdf)

```json
"led_pin": "LED"
```

### Raspberry Pi Pico 2 W

Same pin layout as Pico W. RP2350 chip provides higher clock speed
(150 MHz vs 133 MHz) which benefits software audio mixing.

- **Pico 2 W**: [Buy (The Pi Hut)](https://thepihut.com/products/raspberry-pi-pico-2-w) / [Buy (Pimoroni)](https://shop.pimoroni.com/products/raspberry-pi-pico-2-w) — [Pinout (PDF)](https://datasheets.raspberrypi.com/picow/pico-2-w-pinout.pdf) — [Datasheet](https://datasheets.raspberrypi.com/picow/pico-2-w-datasheet.pdf)

### ESP32-S3 (e.g. Seeed XIAO ESP32-S3)

Different pin naming. Has built-in DAC and more ADC channels. The I2S
pins are configurable (not fixed like on the Pico-Audio HAT). Requires
updating all pin names in `pan_layout.json`.

- **XIAO ESP32-S3**: [Buy (The Pi Hut)](https://thepihut.com/products/seeed-studio-xiao-esp32s3) — [Pinout & getting started](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/) — [Pin multiplexing](https://wiki.seeedstudio.com/xiao_esp32s3_pin_multiplexing/)

```
    ESP32-S3 Pin Mapping
    ┌───────────────────────────────────┐
    │  I2S:  BCK=IO5, LRCK=IO6, DIN=IO7  │
    │  I2C:  SDA=IO8, SCL=IO9            │
    │  GPIO: IO0-IO48 (board-dependent)   │
    │  ADC:  IO1-IO10 (built-in, 12-bit) │
    └───────────────────────────────────┘
```

```json
"i2s": {"bit_clock": "IO5", "word_select": "IO6", "data": "IO7"},
"adc": {"type": "i2c", "sda": "IO8", "scl": "IO9"}
```

**Note:** ESP32-S3 has native I2S support in MicroPython but uses
different API. The rpiPan code uses `machine.I2S` which is available
on both RP2040 and ESP32-S3. External I2S DAC board required (no
Pico-Audio HAT equivalent).

### Arduino Nano RP2040 Connect

RP2040-based with different pin naming (D0-D13, A0-A7). Pin assignments
need remapping. Has built-in IMU and WiFi.

- **Nano RP2040 Connect**: [Buy (The Pi Hut)](https://thepihut.com/products/arduino-nano-rp2040-connect) — [Pinout (PDF)](https://content.arduino.cc/assets/Pinout_NanoRP2040_latest.pdf) — [Hardware docs](https://docs.arduino.cc/hardware/nano-rp2040-connect/) — [Datasheet](https://docs.arduino.cc/resources/datasheets/ABX00053-datasheet.pdf)

```
    Arduino Nano RP2040 Connect Pin Mapping
    ┌─────────────────────────────────────┐
    │  I2S:  BCK=D2, LRCK=D3, DIN=D4     │
    │  I2C:  SDA=A4, SCL=A5              │
    │  GPIO: D0-D13, A0-A7               │
    │  ADC:  A0-A3 (built-in, 12-bit)    │
    └─────────────────────────────────────┘
```

```json
"i2s": {"bit_clock": "D2", "word_select": "D3", "data": "D4"},
"adc": {"type": "i2c", "sda": "A4", "scl": "A5"}
```

**Note:** Requires external I2S DAC board. The pin names must match the
MicroPython `machine` module naming for the Nano RP2040 port.

---

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
- **SW-420 sensitivity**: Adjust the onboard potentiometer. Turn clockwise
  for higher sensitivity (lighter taps trigger). Start with medium.

---

## References

- [Raspberry Pi Pico series documentation hub](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [ADS1115 datasheet (TI)](https://www.ti.com/lit/ds/symlink/ads1115.pdf)
- [Waveshare Pico-Audio wiki](https://www.waveshare.com/wiki/Pico-Audio)
