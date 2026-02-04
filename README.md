# rpiPan

A steel pan instrument running CircuitPython. Designed for the Raspberry Pi Pico H but works on any CircuitPython-compatible board (Pico 2, Pico W, ESP32-S3, Arduino RP2040, etc.). Plays real WAV samples from the [panipuri](https://github.com/profLewis/paniPuri) project with polyphonic playback and velocity-sensitive touch input via analog multiplexers. All 29 notes of a tenor pan using only 9 GPIO pins.

## Features

- **Real steel pan samples** — uses WAV recordings from the [urbanPan](https://github.com/urbansmash/urbanPan) Double Seconds pan
- **Polyphonic playback** — 8 simultaneous voices via CircuitPython `audiomixer`, round-robin allocation with voice stealing
- **Velocity-sensitive input** — analog multiplexer reads strike force (0–3.3V) and maps it to MIDI velocity 1–127
- **JSON-driven configuration** — `pan_layout.json` defines note layout, pin assignments, mux wiring, and audio settings
- **Tenor pan range** — C4 to E6, 29 notes across 3 concentric rings (outer/central/inner)
- **Four input modes** — digital buttons, capacitive touch, mux-based touch with analog velocity, or full analog scan (29 pads, 9 pins)
- **Board auto-detection** — detects Pico, Pico 2, Pico W, ESP32-S3, Arduino RP2040 at startup and applies sensible pin defaults; JSON config overrides as needed
- **Automatic install** — `install.py` converts samples and deploys to the Pico

## Hardware

- Raspberry Pi Pico H (or Pico 2, Pico W, any CircuitPython board)
- Waveshare Pico-Audio HAT (I2S DAC, PCM5101A) — plugs onto Pico
- ADS1115 I2C ADC breakout (16-bit, reads mux analog signals)
- 2x HW-178 multiplexer modules (CD74HC4067 16-channel analog mux breakout)
- 29 FSR (Force Sensitive Resistor) touch pads
- 4W speaker (4-8 ohm) — connects to Pico-Audio speaker header
- See [WIRING.md](WIRING.md) for the full wiring diagram

Alternative: use PWM audio (no HAT needed) with an external amplifier — see WIRING.md.

## Quick Start

### 1. Install CircuitPython

Download CircuitPython for the Pico from [circuitpython.org](https://circuitpython.org/board/raspberry_pi_pico/) and flash it to the board. The Pico will appear as a `CIRCUITPY` USB drive.

### 2. Install rpiPan

```bash
# Clone the repo
git clone https://github.com/profLewis/rpiPan.git
cd rpiPan

# Convert samples and copy everything to the Pico
python install.py /Volumes/CIRCUITPY
```

This converts the panipuri WAV files (44100 Hz stereo) to Pico-friendly format (22050 Hz mono), then copies `code.py`, `pan_layout.json`, and `sounds/` to the drive.

### 2b. Install CircuitPython Libraries (for I2S + ADS1115)

If using the default I2S audio configuration with ADS1115, install the required libraries:

```bash
# Automatic — downloads from the Adafruit Bundle, detects CP version
python install.py --libs-only /Volumes/CIRCUITPY

# Or combine with sample install
python install.py --libs /Volumes/CIRCUITPY

# Or manually using circup
pip install circup
circup install adafruit_ads1x15 adafruit_bus_device
```

The Pico restarts automatically and runs the demo.

### 3. Wire up pads

Connect touch pads and the multiplexer as described in [WIRING.md](WIRING.md), then edit `pan_layout.json` to map GPIO pins to notes.

## Board Auto-Detection

On startup, `code.py` detects the board type and applies sensible default pin assignments. Any settings in `pan_layout.json` override the defaults, so you only need to configure what differs from the standard setup.

| Board | Detected as | I2S Pins | I2C Pins | Mux Select |
|-------|-------------|----------|----------|------------|
| Pico / Pico 2 | `raspberry_pi_pico` | GP26/27/28 | GP4/GP5 | GP10-13 |
| Pico W | `raspberry_pi_pico_w` | GP26/27/28 | GP4/GP5 | GP10-13 |
| ESP32-S3 | `esp32s3` | IO4/5/6 | native ADC | IO10-13 |
| Arduino Nano RP2040 | `arduino_nano_rp2040_connect` | D2/3/4 | A4/A5 | D5-8 |

For most Pico setups, the JSON `"hardware"` section only needs `input_mode` and `pads` — pin assignments are automatic.

## Configuration

All configuration lives in `pan_layout.json`. The `"notes"` section defines the pan layout (same format as panipuri), and the `"hardware"` section configures the Pico:

```json
{
  "notes": [
    {"name": "C", "octave": 4, "ring": "outer", "idx": "O6"},
    {"name": "D", "octave": 4, "ring": "outer", "idx": "O4"}
  ],
  "hardware": {
    "audio_out": "i2s",
    "i2s": {
      "bit_clock": "GP27",
      "word_select": "GP28",
      "data": "GP26"
    },
    "input_mode": "mux_scan",
    "max_voices": 8,
    "sample_rate": 22050,
    "adc": {"type": "i2c", "sda": "GP4", "scl": "GP5"},
    "mux": {
      "select_pins": ["GP10", "GP11", "GP12", "GP13"],
      "mux_a": {"enable_pin": "GP14"},
      "mux_b": {"enable_pin": "GP15"},
      "threshold": 3000
    },
    "pads": [
      {"note": "C4", "mux": "a", "channel": 0},
      {"note": "C#4", "mux": "a", "channel": 1}
    ]
  }
}
```

### Input Modes

| Mode | `input_mode` | Description |
|------|-------------|-------------|
| Mux Scan | `"mux_scan"` | Full 29-pad scan via 2 muxes. Analog threshold triggers, magnitude = velocity. 9 pins. |
| Mux Touch | `"mux_touch"` | Digital trigger + analog velocity via single mux. Up to ~20 pads. |
| Button | `"button"` | Digital GPIO pins with internal pull-up, active low. Fixed velocity. |
| Touch | `"touch"` | Capacitive touch via `touchio`. Fixed velocity. |

**Mux scan mode** — full 29-pad tenor pan, velocity-sensitive, I2S audio via Pico-Audio HAT:

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

**Button mode** — simplest wiring, each pad is a switch to GND:

```json
"input_mode": "button",
"pins": {
  "GP0": "C4",
  "GP1": "D4"
}
```

**Mux touch mode** — velocity-sensitive, each pad has a digital trigger pin and a mux channel for analog reading:

```json
"input_mode": "mux_touch",
"mux": {
  "analog_pin": "GP26",
  "select_pins": ["GP10", "GP11", "GP12", "GP13"]
},
"pins": {
  "GP0": {"note": "C4", "mux_channel": 0},
  "GP1": {"note": "D4", "mux_channel": 1}
}
```

### Hardware Settings

| Key | Default | Description |
|-----|---------|-------------|
| `audio_out` | `"i2s"` | Audio backend: `"i2s"` or `"pwm"` |
| `i2s` | see below | I2S pin config (when `audio_out` is `"i2s"`) |
| `audio_pin` | `"GP18"` | PWM audio output pin (when `audio_out` is `"pwm"`) |
| `adc` | `null` | ADC config: `{"type": "i2c", "sda": "GP4", "scl": "GP5"}` for ADS1115 |
| `max_voices` | `8` | Simultaneous polyphony voices |
| `sample_rate` | `22050` | Audio sample rate in Hz |
| `sounds_dir` | `"sounds"` | Directory containing WAV files |
| `led_pin` | `"LED"` | Activity indicator LED |

### Note Identifiers

Pin mappings accept notes in several formats:

| Format | Example | Description |
|--------|---------|-------------|
| Name + octave | `"C4"`, `"F#5"` | Note name with octave number |
| Layout index | `"O6"`, `"C3"` | Index from the pan layout |
| MIDI number | `"60"`, `"72"` | MIDI note number as string |

## install.py

Converts panipuri's WAV samples and deploys to the Pico.

```bash
python install.py                              # Default: /Volumes/CIRCUITPY
python install.py /Volumes/CIRCUITPY           # Explicit drive path
python install.py --source ../panipuri/sounds  # Custom source directory
python install.py --convert-only               # Convert without copying to drive
python install.py --dry-run                    # Preview without changes
python install.py --force                      # Re-convert even if up to date
python install.py --rate 44100                 # Keep original sample rate
python install.py --libs                       # Also install CircuitPython libraries
python install.py --libs-only                  # Only install libraries
```

The converter uses only the Python standard library — no numpy or scipy required. Converted files are cached in `sounds_converted/` so subsequent runs are fast.

## Pan Layout

The 29 tenor pan notes are arranged across 3 concentric rings:

| Ring | Octave | Notes |
|------|--------|-------|
| Outer | 4 | C, C#, D, E, F, F#, G, Ab, A, Bb, B, Eb |
| Central | 5 | C, C#, D, E, Eb, F, F#, G, Ab, A, Bb, B |
| Inner | 6 | C, C#, D, Eb, E |

## How It Works

1. On boot, `code.py` reads `pan_layout.json` to load the note layout and hardware config
2. WAV files from `sounds/` are loaded via `audiocore.WaveFile` (streamed from flash)
3. An `audiomixer.Mixer` runs continuously on `audiobusio.I2SOut` (or `audiopwmio.PWMAudioOut` for PWM mode)
4. The main loop scans input pins at 50 Hz
5. On touch: the mux reads the analog voltage, maps it to velocity, and triggers `note_on`
6. `note_on` allocates a mixer voice (round-robin), sets volume from velocity (`(vel/127)^0.7`), and plays the WAV
7. Notes decay naturally — no explicit `note_off` needed (like a real steel pan)

If WAV files or `audiomixer` are unavailable, the code falls back to simple PWM tone generation.

## Files

| File | Description |
|------|-------------|
| `code.py` | Main CircuitPython program (copy to Pico as `code.py`) |
| `pan_layout.json` | Note layout + hardware configuration |
| `install.py` | Sample converter and Pico installer |
| `WIRING.md` | Wiring diagram (I2S + ADS1115 + dual mux) |
| `sounds/` | WAV samples (generated by `install.py`) |

## Credits

- Steel pan samples from [urbanPan](https://github.com/urbansmash/urbanPan) by urbansmash
- Sample preparation and synthesis from [panipuri](https://github.com/profLewis/paniPuri)

## License

MIT
