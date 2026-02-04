# rpiPan

A steel pan instrument for the Raspberry Pi Pico. Plays real WAV samples from the [urbanPan](https://github.com/urbansmash/urbanPan) Double Seconds pan project with polyphonic playback and velocity-sensitive touch input via analog multiplexers. All 29 notes of a tenor pan using only 9 GPIO pins. Supports MicroPython (default) and CircuitPython.

## Features

- **Real steel pan samples** — automatically downloads WAV recordings from the [urbanPan](https://github.com/urbansmash/urbanPan) Double Seconds pan
- **Polyphonic playback** — 6 simultaneous voices with software mixing (MicroPython) or 8 voices via `audiomixer` (CircuitPython)
- **Velocity-sensitive input** — analog multiplexer reads strike force (0-3.3V) and maps it to MIDI velocity 1-127
- **JSON-driven configuration** — `pan_layout.json` defines note layout, pin assignments, mux wiring, and audio settings
- **Tenor pan range** — C4 to E6, 29 notes across 3 concentric rings (outer/central/inner)
- **Multiple input modes** — digital buttons, mux-based touch with analog velocity, or full analog scan (29 pads, 9 pins)
- **Board auto-detection** — detects Pico, Pico 2, Pico W at startup and applies sensible pin defaults
- **Automatic install** — `install.py` converts samples and stages files for upload

## Hardware

### Full 29-pad setup (mux_scan mode)

- [Raspberry Pi Pico H](https://thepihut.com/products/raspberry-pi-pico) (or [Pico 2](https://thepihut.com/products/raspberry-pi-pico-2), [Pico W](https://thepihut.com/products/raspberry-pi-pico-w))
- [Waveshare Pico-Audio HAT](https://thepihut.com/products/pico-audio-audio-module-for-raspberry-pi-pico-inc-speakers) (I2S DAC, PCM5101A) — plugs onto Pico ([wiki](https://www.waveshare.com/wiki/Pico-Audio))
- [ADS1115 I2C ADC breakout](https://thepihut.com/products/adafruit-ads1115-16-bit-adc-4-channel-with-programmable-gain-amplifier) (16-bit, reads mux analog signals) ([datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf))
- 2x [HW-178 multiplexer modules](https://www.amazon.co.uk/CD74HC4067-16-Channel-Digital-Multiplexer-Breakout/dp/B06Y1L95GK) (CD74HC4067 16-channel analog mux breakout)
- 29x [FSR](https://thepihut.com/products/round-force-sensitive-resistor-fsr) (Force Sensitive Resistor) touch pads
- Speakers included with Pico-Audio HAT (or any 4-8 ohm speaker)

### Direct sensor setup (direct mode)

- [Raspberry Pi Pico H](https://thepihut.com/products/raspberry-pi-pico) (or [Pico 2](https://thepihut.com/products/raspberry-pi-pico-2), [Pico W](https://thepihut.com/products/raspberry-pi-pico-w))
- [Waveshare Pico-Audio HAT](https://thepihut.com/products/pico-audio-audio-module-for-raspberry-pi-pico-inc-speakers) (I2S DAC, PCM5101A) — plugs onto Pico
- [Seeed Grove Shield for Pi Pico](https://thepihut.com/products/grove-shield-for-raspberry-pi-pico-v1-0) (optional, for easy wiring)
- 7-15x [SW-420 vibration sensor modules](https://www.amazon.co.uk/DollaTek-SW-420-Vibration-Sensor-Arduino/dp/B07DJ5NVSC) or [FSRs](https://thepihut.com/products/round-force-sensitive-resistor-fsr)
- [ADS1115 I2C ADC breakout](https://thepihut.com/products/adafruit-ads1115-16-bit-adc-4-channel-with-programmable-gain-amplifier) (optional, for velocity on up to 4 pads)
- Speakers included with Pico-Audio HAT (or any 4-8 ohm speaker)

See [WIRING.md](WIRING.md) for wiring diagrams for all configurations.

## Quick Start (MicroPython)

### 1. Install MicroPython Firmware

Download the MicroPython UF2 firmware for your board:

- **Pico / Pico H**: [micropython.org/download/RPI_PICO/](https://micropython.org/download/RPI_PICO/)
- **Pico 2**: [micropython.org/download/RPI_PICO2/](https://micropython.org/download/RPI_PICO2/)
- **Pico W**: [micropython.org/download/RPI_PICO_W/](https://micropython.org/download/RPI_PICO_W/)

Flash the firmware:

1. Hold the **BOOTSEL** button on the Pico and plug it into USB
2. The Pico appears as a USB drive called `RPI-RP2`
3. Drag the `.uf2` file onto the drive — the Pico reboots into MicroPython
4. Do not disconnect during flashing

### 2. Install Thonny IDE

[Thonny](https://thonny.org) is the recommended IDE for MicroPython development.

1. Download and install from [thonny.org](https://thonny.org)
2. Open Thonny
3. Go to **Tools > Options > Interpreter**
4. Select **MicroPython (Raspberry Pi Pico)**
5. Select the correct USB serial port
6. Click OK — you should see the MicroPython REPL (`>>>`) at the bottom

### 3. Download, Convert, and Stage Files

```bash
# Clone the repo
git clone https://github.com/profLewis/rpiPan.git
cd rpiPan

# Download sounds from urbanPan, convert, and stage for MicroPython
python install.py

# Or use existing panipuri sounds instead of downloading
python install.py --source ../panipuri/sounds
```

This downloads WAV samples from the urbanPan GitHub repo (25 direct downloads + 4 pitch-shifted), converts them to Pico-friendly format (22050 Hz mono), and stages all files in `micropython_staging/`. No external dependencies needed — uses only Python stdlib.

### 4. Upload to Pico

**Option A: Thonny IDE** (recommended)

1. Open Thonny, connect to your Pico
2. Go to **View > Files** to open the file browser
3. Navigate to the `micropython_staging/` directory on your computer
4. Right-click each file/folder and select **Upload to /**
5. Upload: `main.py`, `pan_layout.json`, and the `sounds/` folder

**Option B: mpremote** (command line)

```bash
pip install mpremote
cd micropython_staging
mpremote fs cp main.py :main.py
mpremote fs cp pan_layout.json :pan_layout.json
mpremote fs cp -r sounds/ :
```

### 5. Run

Reset the Pico (unplug/replug or press the reset button). MicroPython runs `main.py` automatically. Monitor output via Thonny's Shell or `mpremote`.

To run the hardware diagnostic:

1. Upload `test_hw.py` to the Pico
2. In Thonny, open `test_hw.py` on the Pico and click Run (F5)

### 6. Wire up pads

Connect touch pads and the multiplexer as described in [WIRING.md](WIRING.md), then edit `pan_layout.json` to map GPIO pins to notes.

## CircuitPython Alternative

rpiPan also supports CircuitPython. The CircuitPython version uses hardware audio mixing (`audiomixer`) for 8-voice polyphony and supports capacitive touch input.

### CircuitPython Quick Start

1. Download CircuitPython for your board from [circuitpython.org](https://circuitpython.org/board/raspberry_pi_pico/) and flash it. The Pico appears as a `CIRCUITPY` USB drive.

2. Install rpiPan:

```bash
python install.py --platform circuitpython /Volumes/CIRCUITPY
```

3. Install required libraries (for I2S + ADS1115):

```bash
python install.py --platform circuitpython --libs-only /Volumes/CIRCUITPY
```

The Pico restarts automatically and runs the demo.

### MicroPython vs CircuitPython

| Feature | MicroPython (default) | CircuitPython |
|---------|----------------------|---------------|
| Main file | `main.py` | `code.py` |
| Audio mixing | Software (6 voices) | `audiomixer` hardware (8 voices) |
| I2S output | `machine.I2S` | `audiobusio.I2SOut` |
| ADS1115 driver | Built-in (no libraries needed) | External `adafruit_ads1x15` library |
| File transfer | Thonny IDE or mpremote | USB drive (drag-and-drop) |
| Capacitive touch | Not available | `touchio` supported |
| Auto-reload | No (manual reset) | Yes (on file save) |
| IDE | Thonny recommended | Any text editor |

## Board Auto-Detection

On startup, the main program detects the board type and applies sensible default pin assignments. Any settings in `pan_layout.json` override the defaults.

| Board | I2S Pins | I2C Pins | Mux Select | Pinout |
|-------|----------|----------|------------|--------|
| Pico / Pico H | GP26/27/28 | GP4/GP5 | GP10-13 | [PDF](https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf) / [interactive](https://pico.pinout.xyz/) |
| Pico 2 | GP26/27/28 | GP4/GP5 | GP10-13 | [PDF](https://datasheets.raspberrypi.com/pico/Pico-2-Pinout.pdf) / [interactive](https://pico2.pinout.xyz/) |
| Pico W / WH | GP26/27/28 | GP4/GP5 | GP10-13 | [PDF](https://datasheets.raspberrypi.com/picow/PicoW-A4-Pinout.pdf) / [interactive](https://picow.pinout.xyz/) |
| Pico 2 W | GP26/27/28 | GP4/GP5 | GP10-13 | [PDF](https://datasheets.raspberrypi.com/picow/pico-2-w-pinout.pdf) |

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
    "max_voices": 6,
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
| Direct | `"direct"` | GPIO pins with pull-up + optional ADS1115 velocity. For vibration sensors (SW-420), FSRs, buttons via Grove Shield. No mux needed. Up to 15 pads. |
| Button | `"button"` | Digital GPIO pins with internal pull-up, active low. Fixed velocity. |
| Touch | `"touch"` | Capacitive touch via `touchio`. Fixed velocity. CircuitPython only. |

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

**Direct mode** — vibration sensors (SW-420) or FSRs wired directly to GPIO pins via Grove Shield. No mux needed. Up to 4 pads can read velocity via ADS1115:

```json
"input_mode": "direct",
"adc": {"type": "i2c", "sda": "GP4", "scl": "GP5"},
"pads": [
  {"note": "C4",  "pin": "GP16", "adc_channel": 0},
  {"note": "D4",  "pin": "GP17", "adc_channel": 1},
  {"note": "E4",  "pin": "GP18"},
  {"note": "F4",  "pin": "GP19"}
]
```

### Hardware Settings

| Key | Default | Description |
|-----|---------|-------------|
| `audio_out` | `"i2s"` | Audio backend: `"i2s"` or `"pwm"` (CircuitPython only) |
| `i2s` | see below | I2S pin config |
| `audio_pin` | `"GP18"` | PWM audio output pin (CircuitPython `"pwm"` mode) |
| `adc` | `null` | ADC config: `{"type": "i2c", "sda": "GP4", "scl": "GP5"}` for ADS1115 |
| `max_voices` | `6` | Simultaneous polyphony voices (6 recommended for MicroPython, up to 8 for CircuitPython) |
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

Downloads WAV samples from the urbanPan project, converts to Pico format, and deploys.

```bash
python install.py                              # Download + convert + stage (MicroPython)
python install.py --prepare-only               # Just download source sounds
python install.py --source ../panipuri/sounds  # Use existing sounds directory
python install.py --no-download                # Skip downloading, use existing only
python install.py --convert-only               # Convert without deploying
python install.py --dry-run                    # Preview without changes
python install.py --force                      # Re-download and re-convert all
python install.py --rate 44100                 # Keep original sample rate
python install.py --platform circuitpython /Volumes/CIRCUITPY  # CircuitPython
python install.py --platform circuitpython --libs /Volumes/CIRCUITPY  # CP + libraries
```

Sound preparation follows the same cascading approach as [panipuri](https://github.com/profLewis/paniPuri)'s `prepare_sounds.py`:
1. Check if the WAV already exists locally
2. Download forte (layer 2) sample from [urbanPan](https://github.com/urbansmash/urbanPan)
3. Download the octave-below sample and pitch-shift up

Uses only the Python standard library — no numpy or scipy required. Source sounds are cached in `sounds_source/` and converted files in `sounds_converted/` so subsequent runs are fast.

## Pan Layout

The 29 tenor pan notes are arranged across 3 concentric rings:

| Ring | Octave | Notes |
|------|--------|-------|
| Outer | 4 | C, C#, D, E, F, F#, G, Ab, A, Bb, B, Eb |
| Central | 5 | C, C#, D, E, Eb, F, F#, G, Ab, A, Bb, B |
| Inner | 6 | C, C#, D, Eb, E |

## How It Works

### MicroPython

1. On boot, `main.py` reads `pan_layout.json` to load the note layout and hardware config
2. A software audio mixer (`MixEngine`) runs on core 1 via `_thread`
3. WAV files from `sounds/` are streamed in 512-sample chunks through `machine.I2S`
4. The main loop scans input pins at 50 Hz on core 0
5. On touch: the mux reads the analog voltage, maps it to velocity, and queues a `note_on`
6. The mixer reads PCM data from active voices, mixes with fixed-point volume, and writes to I2S
7. Notes decay naturally — no explicit `note_off` needed (like a real steel pan)
8. You can also type note names via the serial console (e.g. `C4`, `c#4`, `Eb5`, `fs5`) to play notes — works in both demo mode and with hardware pads connected

### CircuitPython

1. On boot, `code.py` reads `pan_layout.json` and sets up `audiomixer.Mixer` on `audiobusio.I2SOut`
2. WAV files are loaded via `audiocore.WaveFile` and played through mixer voices
3. The main loop scans input pins at 50 Hz
4. Falls back to PWM tone generation if WAV files or `audiomixer` are unavailable

## Files

| File | Description |
|------|-------------|
| `main_mp.py` | MicroPython main program (deployed as `main.py`) |
| `test_hw_mp.py` | MicroPython hardware diagnostic (deployed as `test_hw.py`) |
| `diskinfo_mp.py` | MicroPython disk space utility (deployed as `diskinfo.py`) |
| `code.py` | CircuitPython main program |
| `test_hw.py` | CircuitPython hardware diagnostic |
| `pan_layout.json` | Note layout + hardware configuration (shared) |
| `install.py` | Sample converter and Pico installer |
| `WIRING.md` | Wiring diagram (I2S + ADS1115 + dual mux) |
| `sounds/` | WAV samples (generated by `install.py`) |

## Troubleshooting

### mpremote: "no device found" or "failed to access" serial port

Thonny holds the Pico's serial port exclusively. **Close Thonny completely** before using `mpremote`. Only one program can use the serial port at a time.

If mpremote still can't find the device, specify the port explicitly:

```bash
# Check the port exists
ls /dev/tty.usbmodem*          # macOS
ls /dev/ttyACM*                # Linux

# Connect with explicit port
mpremote connect /dev/tty.usbmodem2101 run diskinfo_mp.py
mpremote connect /dev/tty.usbmodem2101 fs cp main.py :main.py
```

To check what's using the port:

```bash
lsof /dev/tty.usbmodem*       # macOS
fuser /dev/ttyACM0             # Linux
```

### Pico not detected at all (no serial port)

- Make sure the USB cable is a **data cable**, not charge-only
- MicroPython firmware must be installed first (see Step 1 above)
- Try a different USB port

## Credits

- Steel pan samples from [urbanPan](https://github.com/urbansmash/urbanPan) by urbansmash
- Sample preparation and synthesis from [panipuri](https://github.com/profLewis/paniPuri)

## License

MIT
