# rpiPan

A steel pan instrument running CircuitPython. Designed for the Raspberry Pi Pico / Pico 2 but works on any CircuitPython-compatible board (ESP32-S3, Arduino RP2040, etc.). Plays real WAV samples from the [panipuri](https://github.com/profLewis/paniPuri) project with polyphonic playback and velocity-sensitive touch input via analog multiplexers. All 29 notes of a tenor pan using only 9 GPIO pins.

## Features

- **Real steel pan samples** — uses WAV recordings from the [urbanPan](https://github.com/urbansmash/urbanPan) Double Seconds pan
- **Polyphonic playback** — 8 simultaneous voices via CircuitPython `audiomixer`, round-robin allocation with voice stealing
- **Velocity-sensitive input** — analog multiplexer reads strike force (0–3.3V) and maps it to MIDI velocity 1–127
- **JSON-driven configuration** — `pan_layout.json` defines note layout, pin assignments, mux wiring, and audio settings
- **Tenor pan range** — C4 to E6, 29 notes across 3 concentric rings (outer/central/inner)
- **Four input modes** — digital buttons, capacitive touch, mux-based touch with analog velocity, or full analog scan (29 pads, 9 pins)
- **Board-agnostic** — pin names in JSON config, works on Pico, Pico 2, Pico W, ESP32-S3, Arduino RP2040
- **Automatic install** — `install.py` converts samples and deploys to the Pico

## Hardware

- Raspberry Pi Pico / Pico 2 (or any CircuitPython board)
- 4W speaker via class-D amplifier (e.g. PAM8403) on GP18
- 29 FSR (Force Sensitive Resistor) touch pads
- 2x CD74HC4067 16-channel analog multiplexers
- See [WIRING.md](WIRING.md) for the full wiring diagram

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

The Pico restarts automatically and runs the demo.

### 3. Wire up pads

Connect touch pads and the multiplexer as described in [WIRING.md](WIRING.md), then edit `pan_layout.json` to map GPIO pins to notes.

## Configuration

All configuration lives in `pan_layout.json`. The `"notes"` section defines the pan layout (same format as panipuri), and the `"hardware"` section configures the Pico:

```json
{
  "notes": [
    {"name": "C", "octave": 4, "ring": "outer", "idx": "O6"},
    {"name": "D", "octave": 4, "ring": "outer", "idx": "O4"}
  ],
  "hardware": {
    "audio_pin": "GP18",
    "input_mode": "mux_touch",
    "max_voices": 8,
    "sample_rate": 22050,
    "mux": {
      "analog_pin": "GP26",
      "select_pins": ["GP10", "GP11", "GP12", "GP13"]
    },
    "pins": {
      "GP0": {"note": "C4", "mux_channel": 0},
      "GP1": {"note": "D4", "mux_channel": 1},
      "GP2": {"note": "E4", "mux_channel": 2}
    }
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

**Mux scan mode** — full 29-pad tenor pan, velocity-sensitive, only 9 GPIO pins:

```json
"input_mode": "mux_scan",
"mux": {
  "select_pins": ["GP10", "GP11", "GP12", "GP13"],
  "mux_a": {"analog_pin": "GP26", "enable_pin": "GP14"},
  "mux_b": {"analog_pin": "GP27", "enable_pin": "GP15"},
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
| `audio_pin` | `"GP18"` | PWM audio output pin |
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
3. An `audiomixer.Mixer` runs continuously on `audiopwmio.PWMAudioOut`
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
| `WIRING.md` | Wiring diagram for mux_touch mode |
| `sounds/` | WAV samples (generated by `install.py`) |

## Credits

- Steel pan samples from [urbanPan](https://github.com/urbansmash/urbanPan) by urbansmash
- Sample preparation and synthesis from [panipuri](https://github.com/profLewis/paniPuri)

## License

MIT
