# CLAUDE.md - Project Guide for Claude Code

## Project Overview

rpiPan is a CircuitPython steel pan instrument. Designed for the Raspberry Pi Pico / Pico 2 but works on any board with CircuitPython support (ESP32-S3, Arduino RP2040, etc.). Reads a JSON layout file (`pan_layout.json`) to configure notes and hardware, plays WAV samples with polyphonic mixing, and supports velocity-sensitive touch input via analog multiplexers. All pin names come from the JSON config, so no code changes needed when switching boards.

Companion project to [panipuri](https://github.com/profLewis/paniPuri) (desktop Python version).

## Architecture

- **`code.py`** — Main CircuitPython program. Runs on the Pico. All classes and logic in one file (CircuitPython has limited import support).
- **`install.py`** — Desktop Python script. Converts panipuri WAV samples (44100 Hz stereo → 22050 Hz mono) and deploys to CIRCUITPY drive. Uses only stdlib (`wave`, `struct`, `json`).
- **`pan_layout.json`** — Combined note layout + hardware configuration. Same `"notes"` format as panipuri, plus a `"hardware"` section for Pico pin assignments.

## code.py Structure

### Audio Players

- **`WavPlayer`** — Primary. Uses `audiomixer.Mixer` with either `audiobusio.I2SOut` (default, for Waveshare Pico-Audio HAT) or `audiopwmio.PWMAudioOut` (fallback). 8-voice polyphony, round-robin allocation with voice stealing. Streams WAV files via `audiocore.WaveFile`. Velocity maps to volume via `(vel/127)^0.7`. Constructor accepts `audio_out="i2s"|"pwm"` and optional `i2s_config` dict.
- **`TonePlayer`** — Fallback. Simple PWM square wave. Used when WAV files or audiomixer are unavailable. Only works with PWM audio output.

Both expose the same interface: `note_on(midi, velocity)`, `note_off(midi)`, `all_off()`, `load_all(notes)`, `deinit()`.

### Input Handlers

- **`ButtonInput`** — Digital GPIO with pull-up, active low. Returns notes with no velocity (defaults to 100).
- **`TouchInput`** — Capacitive touch via `touchio`. Returns notes with no velocity.
- **`MuxTouchInput`** — Digital trigger + analog velocity via HW-178 (CD74HC4067) multiplexer. Select pins address the mux channel, ADC reads 0–3.3V, maps linearly to velocity 1–127. Returns notes with `"velocity"` key. Good for up to ~20 pads. Accepts optional `adc_config` for I2C ADC (ADS1115).
- **`MuxScanInput`** — Pure analog scanning via 2x HW-178 (CD74HC4067) with enable pins. No digital trigger pins needed — threshold crossing on the analog reading triggers notes, magnitude gives velocity. Supports all 29 pads. Configured via `"pads"` array (not `"pins"` dict). ADC via native `analogio` or external ADS1115 over I2C (required when I2S audio occupies the ADC pins).

All expose: `scan()` → `(pressed_list, released_list)`, `.count` property.

### Utilities

### ADC Helpers

- `_create_i2c_adc_channel(adc_config, channel_num)` — Creates a single ADS1115 AnalogIn channel
- `_create_i2c_adc_channels(adc_config, count)` — Creates multiple ADS1115 channels on one I2C bus

Both return objects with a `.value` property (0-65535), matching the `analogio.AnalogIn` interface.

### Utilities

- `note_to_midi(name, octave)` — e.g. `("C#", 4)` → `61`
- `midi_to_freq(midi)` — e.g. `60` → `261.6 Hz`
- `midi_to_filename(midi)` — e.g. `60` → `"C4.wav"`, `61` → `"Cs4.wav"`
- `midi_to_display(midi)` — e.g. `60` → `"C4"`, `61` → `"C#4"`
- `load_layout(path)` — Returns `(notes_list, hardware_dict)` from JSON
- `build_note_lookup(notes)` — Returns `(by_name, by_idx, by_midi)` dicts
- `find_note(id, ...)` — Looks up note by name+octave, layout idx, or MIDI number

### Board Detection

- `detect_board()` — Returns board ID string using `board.board_id` (CircuitPython 7+) or pin probing fallback
- `BOARD_DEFAULTS` — Dict of default hardware configs per board type (Pico, Pico 2, Pico W, ESP32-S3, Arduino Nano RP2040)
- `get_board_defaults(board_id)` — Looks up defaults, supports prefix matching (e.g. `raspberry_pi_pico2` matches `raspberry_pi_pico`)
- `_deep_merge(base, override)` — Merges JSON config over board defaults (JSON wins)

On startup, `main()` detects the board, loads defaults, then merges with `pan_layout.json` hardware config. This means minimal JSON config is needed — board-specific pins are filled in automatically.

### Demo Functions

- `play_demo(player, notes, tempo_bpm)` — Plays all notes sequentially
- `play_chord_demo(player, notes)` — Plays C, F, G, C chords

## Key Technical Details

- **Note range**: C4 (MIDI 60) to E6 (MIDI 88) — 29 tenor pan notes
- **Sound naming**: `sounds/{Note}{Octave}.wav`, sharps use lowercase `s` (e.g. `Cs4.wav` = C#4)
- **Audio**: `audiobusio.I2SOut` (default, Pico-Audio HAT) or `audiopwmio.PWMAudioOut` at 22050 Hz, 16-bit mono
- **Polyphony**: 8 voices, round-robin allocation
- **Scan rate**: 50 Hz (20ms per loop)
- **Mux settle time**: 100µs after channel switch before ADC read
- **I2S pins** (Waveshare Pico-Audio): GP26 (DATA), GP27 (BCK), GP28 (LRCK)
- **I2C ADC** (ADS1115): GP4 (SDA), GP5 (SCL), A0=mux_a, A1=mux_b, 860 SPS max
- **Velocity curve**: `(velocity / 127.0) ** 0.7` — same as panipuri

## File Structure

```
code.py              # Main CircuitPython program (runs on Pico)
install.py           # Desktop: convert samples + deploy to Pico
pan_layout.json      # Note layout + hardware config
WIRING.md            # Wiring diagram (I2S + ADS1115 + dual mux)
README.md            # User documentation
CLAUDE.md            # This file
.gitignore           # Excludes sounds_converted/, __pycache__/
sounds_converted/    # Converted WAVs (generated by install.py, not in git)
```

## pan_layout.json Format

```json
{
  "notes": [
    {"name": "C", "octave": 4, "ring": "outer", "idx": "O6"}
  ],
  "hardware": {
    "audio_out": "i2s",
    "i2s": {"bit_clock": "GP27", "word_select": "GP28", "data": "GP26"},
    "input_mode": "mux_scan",
    "max_voices": 8,
    "sample_rate": 22050,
    "sounds_dir": "sounds",
    "led_pin": "LED",
    "adc": {"type": "i2c", "sda": "GP4", "scl": "GP5"},
    "mux": {
      "select_pins": ["GP10", "GP11", "GP12", "GP13"],
      "mux_a": {"enable_pin": "GP14"},
      "mux_b": {"enable_pin": "GP15"},
      "threshold": 3000,
      "settle_us": 100
    },
    "pads": [
      {"note": "C4", "mux": "a", "channel": 0}
    ]
  }
}
```

For PWM audio mode (no I2S HAT), use `"audio_out": "pwm"`, `"audio_pin": "GP18"`, remove `"i2s"` and `"adc"` sections, and add `"analog_pin"` to mux_a/mux_b configs.

Pin values in `"pins"` can be a string (`"C4"`) for button/touch modes or a dict (`{"note": "C4", "mux_channel": 0}`) for mux_touch mode.

## Common Tasks

```bash
# Convert samples only (no Pico needed)
python install.py --convert-only

# Deploy to Pico
python install.py /Volumes/CIRCUITPY

# Preview what install would do
python install.py --dry-run

# Force re-convert all samples
python install.py --force

# Validate JSON
python -c "import json; json.load(open('pan_layout.json')); print('OK')"
```

## Dependencies

### On Pico (CircuitPython)
- `board`, `digitalio` — GPIO
- `audiobusio` — I2S audio output (default)
- `audiopwmio` — PWM audio output (fallback)
- `audiomixer` — polyphonic mixing
- `audiocore` — WAV file streaming
- `analogio` — native ADC reading (PWM audio mode)
- `busio` — I2C bus for ADS1115 (I2S audio mode)
- `adafruit_ads1x15` — ADS1115 I2C ADC driver (external library, I2S mode)
- `adafruit_bus_device` — I2C device abstraction (external library, I2S mode)
- `touchio` — capacitive touch (touch mode, optional)
- `json`, `time` — stdlib

### On Desktop (install.py)
- Python 3.8+
- No external dependencies (stdlib only: `wave`, `struct`, `json`, `shutil`, `argparse`)

## Relationship to panipuri

rpiPan is the embedded/hardware version of panipuri. Key differences:

| | panipuri | rpiPan |
|---|---------|--------|
| Platform | Desktop Python | CircuitPython on Pico |
| Audio | pygame.mixer (44100 Hz stereo) | I2S (Pico-Audio HAT) or PWM + audiomixer (22050 Hz mono) |
| Input | Keyboard, MIDI, song files | GPIO buttons, touch, mux analog |
| Polyphony | 16 voices | 8 voices |
| Synthesis | Full synth engine (synth.py) | WAV samples only (no synthesis) |
| Config | pan_layout.json (notes only) | pan_layout.json (notes + hardware) |
