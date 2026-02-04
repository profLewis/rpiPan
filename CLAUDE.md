# CLAUDE.md - Project Guide for Claude Code

## Project Overview

rpiPan is a steel pan instrument for the Raspberry Pi Pico. Supports MicroPython (default) and CircuitPython. Reads a JSON layout file (`pan_layout.json`) to configure notes and hardware, plays WAV samples with polyphonic mixing, and supports velocity-sensitive touch input via analog multiplexers. All pin names come from the JSON config, so no code changes needed when switching boards.

Companion project to [panipuri](https://github.com/profLewis/paniPuri) (desktop Python version).

## Architecture

### MicroPython (default)

- **`main_mp.py`** — Main MicroPython program. Deployed as `main.py` on the Pico. All classes and logic in one file. Software audio mixing with I2S output via `machine.I2S`. Inline ADS1115 driver (no external libraries).
- **`test_hw_mp.py`** — MicroPython hardware diagnostic. Deployed as `test_hw.py`. Tests: board detection, I2S audio (sine tones), ADS1115 ADC, mux scan, GPIO survey, WAV playback (sequential all notes + polyphonic chords with stagger). All I2C errors reported but don't stop the test run.
- **`diskinfo_mp.py`** — Disk space utility. Deployed as `diskinfo.py`. Lists free/used space and all files with sizes. Can run via `mpremote run diskinfo_mp.py` without copying.

### CircuitPython (alternative)

- **`code.py`** — Main CircuitPython program. Uses `audiomixer.Mixer` for hardware-accelerated polyphony. Requires external libraries (`adafruit_ads1x15`, `adafruit_bus_device`).
- **`test_hw.py`** — CircuitPython hardware diagnostic.

### Shared

- **`install.py`** — Desktop Python script. Downloads WAV samples from urbanPan (cascading fallback: exists → download → pitch-shift from lower octave), converts (44100 Hz stereo -> 22050 Hz mono), and deploys. `--platform micropython` (default) stages files and trims WAVs to fit 1 MB (`--max-sounds-mb`); auto-uploads via mpremote (installs if needed), cleans old files on Pico first (preserves `.txt`). `--platform circuitpython` copies to CIRCUITPY drive. `--source` overrides source directory. Uses only stdlib.
- **`pan_layout.json`** — Combined note layout + hardware configuration. Same format for both platforms.

## main_mp.py Structure (MicroPython)

### Pin Translation

- `pin_num(name)` — Converts CircuitPython-style names from JSON: `"GP10"` -> `10`, `"LED"` -> `25`
- `make_pin(name, mode, pull, value)` — Creates `machine.Pin` from config name string

### Inline ADS1115 Driver

- `ADS1115(i2c, addr)` — Minimal I2C driver for single-ended reads. No external library needed.
- `read_channel(channel)` — Reads channel 0-3, returns 0-65535 (unsigned).
- Config: 860 SPS, +/-4.096V gain, single-shot mode.

### WAV File Reader

- `WavReader(path)` — Opens WAV file, parses 44-byte header, validates 16-bit mono PCM.
- `read_chunk(buf)` — Reads PCM samples into existing `array.array('h')` via `memoryview`. Zero-copy.
- `rewind()` — Seeks back to data start for retriggering.
- Each `Voice` opens its own file handle (max `max_voices` open at once).

### Software Audio Mixer

- **`Voice`** — Per-voice state: `WavReader`, volume (fixed-point 0-256), chunk buffer.
- **`MixEngine`** — Replaces CircuitPython's `audiomixer.Mixer` + `audiocore.WaveFile`.
  - Uses `machine.I2S` for output. Validates WS = SCK + 1 constraint (RP2040 requirement).
  - **Core 1 audio thread** via `_thread`:
    1. Process pending note_on/note_off commands (lock-protected queue)
    2. Read next 512-sample chunk from each active voice's WAV file
    3. Mix with fixed-point volume: `(sample * vol) >> 8`
    4. Clamp to int16, pack to bytes, blocking `i2s.write()`
  - 6 voices default (configurable). Voice allocation: round-robin with voice stealing.
  - Each `note_on` opens a WAV file handle; voice completion closes it.
  - 512-sample chunks = ~23ms at 22050 Hz.

### Input Handlers

- **`ButtonInput`** — `machine.Pin(n, Pin.IN, Pin.PULL_UP)`, `.value()` method.
- **`DirectInput`** — Direct GPIO pins + optional ADS1115 velocity. For vibration sensors (SW-420), FSRs via Grove Shield. No mux needed. Code design and testing: P. Lewis.
- **`MuxTouchInput`** — Digital trigger + mux analog read via inline ADS1115.
- **`MuxScanInput`** — Dual mux scanning via ADS1115, shared select + enable pins.
- **`StdinReader`** — Non-blocking serial input via `select.poll()`. Reads note names from stdin.
- No `TouchInput` — MicroPython lacks `touchio`. Falls back to button mode.
- All I2C reads catch `OSError` (EIO) gracefully — return 0 / default velocity instead of crashing.

All expose: `scan()` -> `(pressed_list, released_list)`, `.count` property.

### Serial Note Input

- `parse_note_input(text)` — Case-insensitive parser: `c#4`, `Cs4`, `eb5`, `FS5` all work.
- `StdinReader` — Uses `select.poll()` with `sys.stdin` for non-blocking character accumulation.
- Active in both demo mode (idle loop) and hardware pad mode (main scan loop).
- Accepts: note name with octave (`C4`, `F#5`), sharps as `#` or `s`, flats as `b`.

### Threading Model

- **Core 0** (main thread): Input scanning + stdin polling at 50 Hz. Sends note commands via lock-protected queue.
- **Core 1** (audio thread via `_thread`): Mixing loop. Reads WAV chunks, mixes, writes to I2S.
- Communication: `_pending_on` / `_pending_off` lists protected by `_thread.allocate_lock()`.

## code.py Structure (CircuitPython)

### Audio Players

- **`WavPlayer`** — Primary. Uses `audiomixer.Mixer` with `audiobusio.I2SOut` (default) or `audiopwmio.PWMAudioOut` (fallback). 8-voice polyphony, round-robin allocation with voice stealing. Streams WAV files via `audiocore.WaveFile`. Velocity maps to volume via `(vel/127)^0.7`.
- **`TonePlayer`** — Fallback. Simple PWM square wave. Used when WAV files or audiomixer are unavailable.

Both expose: `note_on(midi, velocity)`, `note_off(midi)`, `all_off()`, `load_all(notes)`, `deinit()`.

### Input Handlers

- **`ButtonInput`** — Digital GPIO with pull-up, active low.
- **`TouchInput`** — Capacitive touch via `touchio`.
- **`MuxTouchInput`** — Digital trigger + analog velocity via multiplexer.
- **`MuxScanInput`** — Pure analog scanning via dual muxes.

### ADC Helpers

- `_create_i2c_adc_channel(adc_config, channel_num)` — Creates a single ADS1115 AnalogIn channel
- `_create_i2c_adc_channels(adc_config, count)` — Creates multiple ADS1115 channels on one I2C bus

### Board Detection

- `detect_board()` — Returns board ID string using `board.board_id` (CircuitPython 7+) or pin probing
- `BOARD_DEFAULTS` — Dict of defaults per board type (Pico H, Pico 2, Pico W, ESP32-S3, Arduino Nano RP2040)
- `get_board_defaults(board_id)` — Prefix matching lookup
- `_deep_merge(base, override)` — Merges JSON config over board defaults

### Utilities (shared logic)

- `note_to_midi(name, octave)` — e.g. `("C#", 4)` -> `61`
- `midi_to_freq(midi)` — e.g. `60` -> `261.6 Hz`
- `midi_to_filename(midi)` — e.g. `60` -> `"C4.wav"`, `61` -> `"Cs4.wav"`
- `midi_to_display(midi)` — e.g. `60` -> `"C4"`, `61` -> `"C#4"`
- `load_layout(path)` — Returns `(notes_list, hardware_dict)` from JSON
- `build_note_lookup(notes)` — Returns `(by_name, by_idx, by_midi)` dicts
- `find_note(id, ...)` — Looks up note by name+octave, layout idx, or MIDI number

### Demo Functions

- `play_demo(player, notes, tempo_bpm)` — Plays all notes sequentially
- `play_chord_demo(player, notes)` — Plays C, F, G, C chords

## Key Technical Details

- **Note range**: C4 (MIDI 60) to E6 (MIDI 88) — 29 tenor pan notes
- **Sound naming**: `sounds/{Note}{Octave}.wav`, sharps use lowercase `s` (e.g. `Cs4.wav` = C#4)
- **Audio**: I2S via Pico-Audio HAT at 22050 Hz, 16-bit mono
- **Polyphony**: 6 voices (MicroPython) / 8 voices (CircuitPython), round-robin allocation
- **Scan rate**: 50 Hz (20ms per loop)
- **Mux settle time**: 100us after channel switch before ADC read
- **I2S pins** (Waveshare Pico-Audio): GP26 (DATA), GP27 (BCK), GP28 (LRCK)
- **I2C ADC** (ADS1115): GP4 (SDA), GP5 (SCL), A0=mux_a, A1=mux_b, 860 SPS max
- **Velocity curve**: `(velocity / 127.0) ** 0.7` — same as panipuri

## File Structure

```
main_mp.py           # MicroPython main (deployed as main.py)
test_hw_mp.py        # MicroPython diagnostic (deployed as test_hw.py)
diskinfo_mp.py       # MicroPython disk space utility (deployed as diskinfo.py)
code.py              # CircuitPython main (deployed as code.py)
test_hw.py           # CircuitPython diagnostic
install.py           # Desktop: download, convert, deploy sounds to Pico
pan_layout.json      # Note layout + hardware config (shared)
WIRING.md            # Wiring diagram (I2S + ADS1115 + dual mux)
README.md            # User documentation
CLAUDE.md            # This file
.gitignore           # Excludes sounds_source/, sounds_converted/, micropython_staging/, __pycache__/
sounds_source/       # Downloaded WAVs from urbanPan (generated by install.py, not in git)
sounds_converted/    # Converted WAVs (generated by install.py, not in git)
micropython_staging/ # Staged MP files for upload (generated by install.py, not in git)
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
    "max_voices": 6,
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

Pin values in `"pins"` can be a string (`"C4"`) for button modes or a dict (`{"note": "C4", "mux_channel": 0}`) for mux_touch mode.

## Common Tasks

```bash
# Download sounds from urbanPan, convert, and stage for MicroPython (default)
python install.py

# Just download/prepare source sounds (no conversion or deploy)
python install.py --prepare-only

# Use existing panipuri sounds instead of downloading
python install.py --source ../panipuri/sounds

# Deploy to CircuitPython Pico
python install.py --platform circuitpython /Volumes/CIRCUITPY

# Convert samples only (no Pico needed)
python install.py --convert-only

# Skip downloading, use existing source files only
python install.py --no-download

# Preview what install would do
python install.py --dry-run

# Force re-download and re-convert all samples
python install.py --force

# Validate JSON
python -c "import json; json.load(open('pan_layout.json')); print('OK')"
```

## Dependencies

### On Pico (MicroPython) — default
- `machine` — Pin, I2C, I2S, ADC
- `_thread` — dual-core audio mixing
- `json`, `time`, `sys`, `os`, `array`, `struct` — stdlib
- No external libraries needed

### On Pico (CircuitPython)
- `board`, `digitalio` — GPIO
- `audiobusio` — I2S audio output
- `audiopwmio` — PWM audio output (fallback)
- `audiomixer` — polyphonic mixing
- `audiocore` — WAV file streaming
- `analogio` — native ADC reading (PWM mode)
- `busio` — I2C bus for ADS1115
- `adafruit_ads1x15` — ADS1115 I2C ADC driver (external library)
- `adafruit_bus_device` — I2C device abstraction (external library)
- `touchio` — capacitive touch (touch mode, optional)

### On Desktop (install.py)
- Python 3.8+
- No external dependencies (stdlib only: `wave`, `struct`, `json`, `shutil`, `argparse`, `urllib`)
- Downloads source WAV samples from urbanPan GitHub automatically

## Sample Source

Original audio samples are from the [urbanPan](https://github.com/urbansmash/urbanPan) project.
`install.py` downloads layer-2 (forte) samples directly from the urbanPan GitHub repo.
For the highest 4 notes (C#6, D6, Eb6, E6) where urbanPan has no direct samples,
`install.py` downloads the octave-below sample and pitch-shifts it up (stdlib only, no numpy/scipy).

## Relationship to panipuri

rpiPan is the embedded/hardware version of panipuri. Both download from the same urbanPan source.
Key differences:

| | panipuri | rpiPan (MicroPython) | rpiPan (CircuitPython) |
|---|---------|---------------------|----------------------|
| Platform | Desktop Python | MicroPython on Pico | CircuitPython on Pico |
| Audio | pygame.mixer (44100 Hz stereo) | machine.I2S + software mixing | audiomixer + I2S/PWM |
| Input | Keyboard, MIDI, song files | GPIO buttons, mux analog | GPIO buttons, touch, mux analog |
| Polyphony | 16 voices | 6 voices | 8 voices |
| Synthesis | Full synth engine (synth.py) | WAV samples only | WAV samples only |
| Config | pan_layout.json (notes only) | pan_layout.json (notes + hardware) | pan_layout.json (notes + hardware) |
