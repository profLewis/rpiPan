"""
rpiPan - Steel Pan instrument for Raspberry Pi Pico (MicroPython)

Reads pan_layout.json to configure note layout, plays WAV samples with
polyphonic software mixing via machine.I2S, responds to touch or button
inputs. Supports velocity-sensitive playback via analog multiplexers.

Hardware:
    - Raspberry Pi Pico H (or Pico 2, Pico W, any MicroPython board)
    - Waveshare Pico-Audio HAT (I2S DAC on GP26/GP27/GP28) — default
    - ADS1115 I2C ADC (when I2S audio occupies the ADC pins)
    - 2x HW-178 (CD74HC4067) analog multiplexers for 29 FSR pads

Input modes:
    - "button"    : digital GPIO pins, fixed velocity
    - "mux_touch" : digital trigger + analog velocity via multiplexer
    - "mux_scan"  : pure analog scanning (2 muxes, no digital pins needed)

Audio output:
    - I2S via machine.I2S (Waveshare Pico-Audio HAT, etc.)

Setup:
    1. Install MicroPython on the Pico
    2. Copy this file as main.py to the Pico (via Thonny or mpremote)
    3. Copy pan_layout.json to the Pico
    4. Copy sounds/ directory with WAV files to the Pico
       (WAV files: 16-bit signed, mono, 22050 Hz — use install.py to convert)

The sounds/ directory should contain files named like the panipuri project:
    C4.wav, Cs4.wav, D4.wav, Ds4.wav, E4.wav, F4.wav, Fs4.wav, ...
    (sharps use lowercase 's': Cs = C#, Fs = F#, etc.)
"""

import json
import time
import sys
import struct
import array
import machine
import _thread
import os


# ---------------------------------------------------------------------------
# Pin translation
# ---------------------------------------------------------------------------

def pin_num(name):
    """Convert a CircuitPython-style pin name to an integer GPIO number.

    'GP10' -> 10, 'GP4' -> 4, 'LED' -> 25, '10' -> 10
    """
    if name == "LED":
        return 25
    if name.startswith("GP"):
        return int(name[2:])
    return int(name)


def make_pin(name, mode=None, pull=None, value=None):
    """Create a machine.Pin from a config pin name string."""
    n = pin_num(name)
    args = [n]
    if mode is not None:
        args.append(mode)
    kwargs = {}
    if pull is not None:
        kwargs["pull"] = pull
    if value is not None:
        kwargs["value"] = value
    return machine.Pin(*args, **kwargs)


# ---------------------------------------------------------------------------
# Board detection
# ---------------------------------------------------------------------------

def detect_board():
    """Detect the board type. Returns a name string."""
    if sys.platform == "rp2":
        try:
            import network
            return "raspberry_pi_pico_w"
        except ImportError:
            pass
        return "raspberry_pi_pico"
    return "unknown_{}".format(sys.platform)


BOARD_DEFAULTS = {
    "raspberry_pi_pico": {
        "audio_out": "i2s",
        "i2s": {"bit_clock": "GP27", "word_select": "GP28", "data": "GP26"},
        "adc": {"type": "i2c", "sda": "GP4", "scl": "GP5"},
        "led_pin": "LED",
        "max_voices": 6,
        "mux": {
            "select_pins": ["GP10", "GP11", "GP12", "GP13"],
            "mux_a": {"enable_pin": "GP14"},
            "mux_b": {"enable_pin": "GP15"},
        },
    },
}
# Pico W shares the same pinout
BOARD_DEFAULTS["raspberry_pi_pico_w"] = dict(BOARD_DEFAULTS["raspberry_pi_pico"])


def get_board_defaults(board_id):
    """Get default hardware config for the detected board."""
    if board_id in BOARD_DEFAULTS:
        return BOARD_DEFAULTS[board_id]
    for key in BOARD_DEFAULTS:
        if board_id.startswith(key):
            return BOARD_DEFAULTS[key]
    return BOARD_DEFAULTS.get("raspberry_pi_pico", {})


# ---------------------------------------------------------------------------
# Note/frequency utilities
# ---------------------------------------------------------------------------

NOTE_NAMES = {
    "C": 0, "C#": 1, "Db": 1,
    "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5,
    "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11, "B#": 0,
}

NOTE_NAMES_FILE = ["C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"]

NOTE_NAMES_DISPLAY = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
]


def note_to_midi(name, octave):
    """Convert note name and octave to MIDI note number."""
    semitone = NOTE_NAMES.get(name)
    if semitone is None:
        return None
    return (octave + 1) * 12 + semitone


def midi_to_freq(midi_note):
    """Convert MIDI note number to frequency in Hz (A4 = 440 Hz)."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def midi_to_filename(midi_note):
    """Convert MIDI note to WAV filename (e.g. 60 -> 'C4.wav')."""
    octave = (midi_note // 12) - 1
    note_idx = midi_note % 12
    return "{}{}.wav".format(NOTE_NAMES_FILE[note_idx], octave)


def midi_to_display(midi_note):
    """Convert MIDI note to display name (e.g. 60 -> 'C4')."""
    octave = (midi_note // 12) - 1
    note_idx = midi_note % 12
    return "{}{}".format(NOTE_NAMES_DISPLAY[note_idx], octave)


# ---------------------------------------------------------------------------
# Layout loader
# ---------------------------------------------------------------------------

def load_layout(path="pan_layout.json"):
    """Load pan layout from JSON file.

    Returns a list of note dicts sorted by MIDI number, each with:
        name, octave, ring, idx, midi, freq, filename
    """
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except OSError:
        print("ERROR: pan_layout.json not found")
        return [], {}

    notes = []
    for entry in data.get("notes", []):
        name = entry["name"]
        octave = entry["octave"]
        midi = note_to_midi(name, octave)
        if midi is not None:
            entry["midi"] = midi
            entry["freq"] = midi_to_freq(midi)
            entry["filename"] = midi_to_filename(midi)
            notes.append(entry)

    notes.sort(key=lambda n: n["midi"])

    hw = data.get("hardware", {})
    return notes, hw


# ---------------------------------------------------------------------------
# Inline ADS1115 I2C ADC driver
# ---------------------------------------------------------------------------

class ADS1115:
    """Minimal ADS1115 driver for single-ended reads.

    No external library required. Reads channels A0-A3 at 860 SPS,
    +/-4.096V gain. Returns 0-65535 (unsigned, matching analogio interface).
    """

    _CONV_REG = 0x00
    _CONF_REG = 0x01
    _ADDR = 0x48

    # Config bits for single-ended channels A0-A3
    _MUX = [0x4000, 0x5000, 0x6000, 0x7000]

    # PGA +/-4.096V = 0x0200, 860 SPS = 0x00E0, single-shot = 0x8100
    _BASE_CONFIG = 0x8100 | 0x0200 | 0x00E0 | 0x0003  # OS|PGA|DR|COMP_QUE

    def __init__(self, i2c, addr=0x48):
        self.i2c = i2c
        self.addr = addr
        self._buf = bytearray(2)

    def read_channel(self, channel):
        """Read a single-ended channel (0-3). Returns 0-65535."""
        config = self._BASE_CONFIG | self._MUX[channel]
        # Write config register (start single-shot conversion)
        self._buf[0] = (config >> 8) & 0xFF
        self._buf[1] = config & 0xFF
        self.i2c.writeto_mem(self.addr, self._CONF_REG, self._buf)

        # Wait for conversion (860 SPS = ~1.2ms per conversion)
        time.sleep_ms(2)

        # Poll until conversion complete (bit 15 of config = 1)
        for _ in range(10):
            self.i2c.readfrom_mem_into(self.addr, self._CONF_REG, self._buf)
            if self._buf[0] & 0x80:
                break
            time.sleep_us(200)

        # Read conversion result (signed 16-bit, big-endian)
        self.i2c.readfrom_mem_into(self.addr, self._CONV_REG, self._buf)
        raw = (self._buf[0] << 8) | self._buf[1]
        if raw >= 0x8000:
            raw -= 0x10000

        # Convert signed (-32768..32767) to unsigned (0..65535)
        return raw + 32768


# ---------------------------------------------------------------------------
# WAV file reader
# ---------------------------------------------------------------------------

class WavReader:
    """Reads 16-bit mono PCM WAV files in chunks for streaming playback."""

    def __init__(self, path):
        self.file = open(path, "rb")
        header = self.file.read(44)

        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            self.file.close()
            raise ValueError("Not a WAV file: {}".format(path))

        # Parse format chunk
        fmt_code = header[20] | (header[21] << 8)
        channels = header[22] | (header[23] << 8)
        sample_rate = (header[24] | (header[25] << 8) |
                       (header[26] << 16) | (header[27] << 24))
        bits = header[34] | (header[35] << 8)

        if fmt_code != 1:
            self.file.close()
            raise ValueError("Not PCM format")
        if channels != 1 or bits != 16:
            self.file.close()
            raise ValueError("Must be 16-bit mono, got {}ch {}bit".format(
                channels, bits))

        self.sample_rate = sample_rate

        # Find data chunk size
        self.data_len = (header[40] | (header[41] << 8) |
                         (header[42] << 16) | (header[43] << 24))
        self.data_start = 44
        self.pos = 0

    def read_chunk(self, buf):
        """Read up to len(buf) samples into buf (array.array('h')).

        Returns number of samples actually read. 0 means end of file.
        """
        remaining = (self.data_len - self.pos) // 2
        to_read = min(len(buf), remaining)
        if to_read <= 0:
            return 0

        n_bytes = to_read * 2
        raw = self.file.read(n_bytes)
        actual = len(raw) // 2
        if actual == 0:
            return 0

        # Copy raw bytes into array via memoryview
        mv = memoryview(buf)
        mv_bytes = mv.cast("B")
        mv_bytes[:len(raw)] = raw
        self.pos += len(raw)
        return actual

    def rewind(self):
        """Seek back to the start of audio data."""
        self.file.seek(self.data_start)
        self.pos = 0

    def close(self):
        """Close the file handle."""
        try:
            self.file.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Software audio mixer with I2S output
# ---------------------------------------------------------------------------

CHUNK_SIZE = 512  # samples per mixing chunk (~23ms at 22050 Hz)


class Voice:
    """Single playback voice — streams from a WAV file."""

    def __init__(self, chunk_size):
        self.reader = None
        self.active = False
        self.volume = 0  # fixed-point 0-256 (256 = 1.0)
        self.midi_note = None
        self.buf = array.array("h", [0] * chunk_size)

    def start(self, path, volume_fp, midi_note):
        """Start playing a WAV file."""
        self.stop()
        try:
            self.reader = WavReader(path)
            self.volume = volume_fp
            self.midi_note = midi_note
            self.active = True
        except Exception as e:
            print("Voice start error: {}".format(e))
            self.active = False

    def stop(self):
        """Stop playback and close file."""
        self.active = False
        self.midi_note = None
        if self.reader:
            self.reader.close()
            self.reader = None

    def fill_buffer(self):
        """Read next chunk. Returns samples read (0 = voice done)."""
        if not self.active or not self.reader:
            return 0
        n = self.reader.read_chunk(self.buf)
        if n == 0:
            self.active = False
        return n


class MixEngine:
    """Polyphonic WAV player with software mixing on I2S output.

    Runs the mixing loop on core 1 via _thread. The main thread
    sends note_on/note_off commands through a lock-protected queue.
    """

    def __init__(self, i2s_config=None, max_voices=6, sample_rate=22050,
                 sounds_dir="sounds"):
        self.sounds_dir = sounds_dir
        self.max_voices = max_voices
        self.sample_rate = sample_rate

        # I2S output
        cfg = i2s_config or {}
        sck = pin_num(cfg.get("bit_clock", "GP27"))
        ws = pin_num(cfg.get("word_select", "GP28"))
        sd = pin_num(cfg.get("data", "GP26"))

        if ws != sck + 1:
            print("WARNING: MicroPython I2S requires WS = SCK + 1")
            print("  SCK={}, WS={} — WS should be {}".format(sck, ws, sck + 1))

        self.i2s = machine.I2S(
            0,
            sck=machine.Pin(sck),
            ws=machine.Pin(ws),
            sd=machine.Pin(sd),
            mode=machine.I2S.TX,
            bits=16,
            format=machine.I2S.MONO,
            rate=sample_rate,
            ibuf=CHUNK_SIZE * 4,
        )

        # Voices
        self.voices = [Voice(CHUNK_SIZE) for _ in range(max_voices)]
        self._next_voice = 0

        # WAV file path cache: midi_note -> file path
        self._path_cache = {}

        # Mix output buffers
        self._mix_buf = array.array("h", [0] * CHUNK_SIZE)
        self._out_bytes = bytearray(CHUNK_SIZE * 2)

        # Thread communication
        self._lock = _thread.allocate_lock()
        self._running = False
        self._pending_on = []
        self._pending_off = []

    def load_note(self, midi_note, filename):
        """Register a WAV file path for a note. Returns True if file exists."""
        path = "{}/{}".format(self.sounds_dir, filename)
        try:
            os.stat(path)
            self._path_cache[midi_note] = path
            return True
        except OSError:
            return False

    def load_all(self, notes):
        """Load WAV file paths for all notes in the layout."""
        loaded = 0
        missing = 0
        for note in notes:
            if self.load_note(note["midi"], note["filename"]):
                loaded += 1
            else:
                missing += 1
                print("  Missing: {}".format(note["filename"]))
        print("Loaded {}/{} WAV samples".format(loaded, loaded + missing))
        return loaded

    def note_on(self, midi_note, velocity=100):
        """Queue a note-on event (called from main thread)."""
        vol_fp = int(((velocity / 127.0) ** 0.7) * 256)
        self._lock.acquire()
        self._pending_on.append((midi_note, vol_fp))
        self._lock.release()

    def note_off(self, midi_note):
        """Queue a note-off event (called from main thread)."""
        self._lock.acquire()
        self._pending_off.append(midi_note)
        self._lock.release()

    def all_off(self):
        """Stop all voices immediately."""
        self._lock.acquire()
        for v in self.voices:
            v.stop()
        self._lock.release()

    def _alloc_voice(self):
        """Allocate a mixer voice using round-robin."""
        voice = self._next_voice
        self._next_voice = (self._next_voice + 1) % self.max_voices
        return voice

    def _find_voice(self, midi_note):
        """Find which voice is playing a given note, or -1."""
        for i, v in enumerate(self.voices):
            if v.midi_note == midi_note:
                return i
        return -1

    def _process_commands(self):
        """Process pending note commands from the main thread."""
        self._lock.acquire()
        on_cmds = list(self._pending_on)
        off_cmds = list(self._pending_off)
        self._pending_on.clear()
        self._pending_off.clear()
        self._lock.release()

        for midi, vol_fp in on_cmds:
            path = self._path_cache.get(midi)
            if path is None:
                continue
            # Stop if already playing
            existing = self._find_voice(midi)
            if existing >= 0:
                self.voices[existing].stop()
            # Allocate and start
            idx = self._alloc_voice()
            self.voices[idx].stop()
            self.voices[idx].start(path, vol_fp, midi)

        for midi in off_cmds:
            idx = self._find_voice(midi)
            if idx >= 0:
                self.voices[idx].stop()

    def _mix_one_chunk(self):
        """Mix all active voices into output buffer and write to I2S."""
        mix = self._mix_buf

        # Zero the mix buffer
        for i in range(CHUNK_SIZE):
            mix[i] = 0

        active_count = 0
        for voice in self.voices:
            if not voice.active:
                continue
            n = voice.fill_buffer()
            if n == 0:
                continue
            active_count += 1
            vol = voice.volume
            vbuf = voice.buf
            for i in range(n):
                mix[i] += (vbuf[i] * vol) >> 8

        # Clamp and apply headroom
        if active_count > 3:
            shift = 2
        elif active_count > 1:
            shift = 1
        else:
            shift = 0

        for i in range(CHUNK_SIZE):
            s = mix[i] >> shift
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            mix[i] = s

        # Pack int16 array to bytes for I2S
        struct.pack_into("<{}h".format(CHUNK_SIZE), self._out_bytes, 0, *mix)

        # Blocking write to I2S
        self.i2s.write(self._out_bytes)

    def _audio_loop(self):
        """Audio mixing loop — runs on core 1."""
        while self._running:
            self._process_commands()
            self._mix_one_chunk()

    def start(self):
        """Start the audio thread on core 1."""
        self._running = True
        _thread.start_new_thread(self._audio_loop, ())

    def stop(self):
        """Stop the audio thread."""
        self._running = False
        time.sleep_ms(100)

    def deinit(self):
        """Clean up audio resources."""
        self.stop()
        self.all_off()
        try:
            self.i2s.deinit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Input handlers
# ---------------------------------------------------------------------------

def build_note_lookup(notes):
    """Build lookup dicts for finding notes by name+octave, idx, or MIDI."""
    by_name = {}
    by_idx = {}
    by_midi = {}
    for n in notes:
        key = "{}{}".format(n["name"], n["octave"])
        by_name[key] = n
        by_idx[n.get("idx", "")] = n
        by_midi[str(n["midi"])] = n
    return by_name, by_idx, by_midi


def find_note(note_id, by_name, by_idx, by_midi):
    """Find a note by name+octave, idx, or MIDI number string."""
    note_id = str(note_id)
    return by_name.get(note_id) or by_idx.get(note_id) or by_midi.get(note_id)


class ButtonInput:
    """Reads GPIO pins as buttons (active low, internal pull-up)."""

    def __init__(self, pin_map, notes):
        self.buttons = []
        by_name, by_idx, by_midi = build_note_lookup(notes)

        for pin_name, note_id in pin_map.items():
            note_info = find_note(note_id, by_name, by_idx, by_midi)
            if note_info is None:
                print("WARNING: Note {} not in layout".format(note_id))
                continue
            try:
                pin = make_pin(pin_name, machine.Pin.IN, pull=machine.Pin.PULL_UP)
                self.buttons.append({
                    "pin": pin,
                    "note": note_info,
                    "was_pressed": False,
                })
            except Exception as e:
                print("WARNING: {} init failed: {}".format(pin_name, e))

    def scan(self):
        """Returns (pressed_notes, released_notes) lists."""
        pressed = []
        released = []
        for btn in self.buttons:
            is_pressed = not btn["pin"].value()
            if is_pressed and not btn["was_pressed"]:
                pressed.append(btn["note"])
            elif not is_pressed and btn["was_pressed"]:
                released.append(btn["note"])
            btn["was_pressed"] = is_pressed
        return pressed, released

    @property
    def count(self):
        return len(self.buttons)


class MuxTouchInput:
    """Digital touch trigger + analog velocity via multiplexer.

    Each pad has a digital GPIO pin for touch detection and a channel
    on an analog multiplexer (HW-178 / CD74HC4067) for reading
    strike intensity.

    Uses inline ADS1115 driver (I2C) or native ADC for analog reads.
    """

    def __init__(self, pin_map, notes, mux_config, adc_config=None):
        self.pads = []
        by_name, by_idx, by_midi = build_note_lookup(notes)

        # Set up ADC
        adc_type = adc_config.get("type", "native") if adc_config else "native"
        if adc_type == "i2c":
            sda = pin_num(adc_config.get("sda", "GP4"))
            scl = pin_num(adc_config.get("scl", "GP5"))
            i2c = machine.I2C(0, scl=machine.Pin(scl), sda=machine.Pin(sda),
                              freq=400000)
            self.ads = ADS1115(i2c)
            self.adc_channel = 0
            self.adc_type = "i2c"
            print("Mux ADC: ADS1115 channel A0 via I2C")
        else:
            adc_pin_name = mux_config.get("analog_pin", "GP26")
            self.native_adc = machine.ADC(machine.Pin(pin_num(adc_pin_name)))
            self.adc_type = "native"

        # Set up mux select pins
        self.select_pins = []
        for sp_name in mux_config.get("select_pins", []):
            pin = make_pin(sp_name, machine.Pin.OUT, value=0)
            self.select_pins.append(pin)
        self.num_select = len(self.select_pins)
        print("Mux: {} select pins".format(self.num_select))

        # Set up per-pad digital trigger + mux channel
        for pin_name, pad_cfg in pin_map.items():
            if isinstance(pad_cfg, str):
                note_id = pad_cfg
                mux_ch = None
            else:
                note_id = pad_cfg.get("note", "")
                mux_ch = pad_cfg.get("mux_channel")

            note_info = find_note(note_id, by_name, by_idx, by_midi)
            if note_info is None:
                print("WARNING: Note {} not in layout".format(note_id))
                continue

            try:
                pin = make_pin(pin_name, machine.Pin.IN, pull=machine.Pin.PULL_UP)
                self.pads.append({
                    "pin": pin,
                    "note": note_info,
                    "mux_channel": mux_ch,
                    "was_pressed": False,
                })
            except Exception as e:
                print("WARNING: {} init failed: {}".format(pin_name, e))

    def _set_mux_channel(self, channel):
        for i in range(self.num_select):
            self.select_pins[i].value(1 if (channel & (1 << i)) else 0)

    def _read_velocity(self, channel):
        if channel is None or self.num_select == 0:
            return 100
        self._set_mux_channel(channel)
        time.sleep_us(1000)
        if self.adc_type == "i2c":
            raw = self.ads.read_channel(self.adc_channel)
        else:
            raw = self.native_adc.read_u16()
        velocity = int((raw / 65535.0) * 126) + 1
        return max(1, min(127, velocity))

    def scan(self):
        pressed = []
        released = []
        for pad in self.pads:
            is_pressed = not pad["pin"].value()
            if is_pressed and not pad["was_pressed"]:
                vel = self._read_velocity(pad["mux_channel"])
                note_with_vel = dict(pad["note"])
                note_with_vel["velocity"] = vel
                pressed.append(note_with_vel)
            elif not is_pressed and pad["was_pressed"]:
                released.append(pad["note"])
            pad["was_pressed"] = is_pressed
        return pressed, released

    @property
    def count(self):
        return len(self.pads)


class MuxScanInput:
    """Pure analog scanning via dual HW-178 (CD74HC4067) multiplexers.

    No digital trigger pins needed. Threshold crossing on the analog
    reading triggers notes; magnitude gives velocity. Supports all 29 pads.
    ADC via ADS1115 I2C (required when I2S occupies the native ADC pins).
    """

    def __init__(self, notes, mux_config, pads_config, adc_config=None):
        self.pads = []
        by_name, by_idx, by_midi = build_note_lookup(notes)

        self.threshold = mux_config.get("threshold", 3000)
        self.settle_us = mux_config.get("settle_us", 100)

        # Shared mux select pins
        self.select_pins = []
        for sp_name in mux_config.get("select_pins", []):
            pin = make_pin(sp_name, machine.Pin.OUT, value=0)
            self.select_pins.append(pin)
        self.num_select = len(self.select_pins)

        # ADC
        mux_a_cfg = mux_config.get("mux_a", {})
        mux_b_cfg = mux_config.get("mux_b", {})
        self.ads = None
        self.adc_a_ch = 0
        self.adc_b_ch = 1
        self.native_adc_a = None
        self.native_adc_b = None

        adc_type = adc_config.get("type", "native") if adc_config else "native"
        if adc_type == "i2c":
            sda = pin_num(adc_config.get("sda", "GP4"))
            scl = pin_num(adc_config.get("scl", "GP5"))
            i2c = machine.I2C(0, scl=machine.Pin(scl), sda=machine.Pin(sda),
                              freq=400000)
            self.ads = ADS1115(i2c)
            print("Mux ADC: ADS1115 A0=mux_a, A1=mux_b via I2C")
        else:
            a_pin = mux_a_cfg.get("analog_pin", "GP26")
            b_pin = mux_b_cfg.get("analog_pin", "GP27")
            self.native_adc_a = machine.ADC(machine.Pin(pin_num(a_pin)))
            self.native_adc_b = machine.ADC(machine.Pin(pin_num(b_pin)))

        # Enable pins
        self.en_a = None
        self.en_b = None
        a_en_name = mux_a_cfg.get("enable_pin", "GP14")
        b_en_name = mux_b_cfg.get("enable_pin", "GP15")
        try:
            self.en_a = make_pin(a_en_name, machine.Pin.OUT, value=1)
        except Exception:
            pass
        try:
            self.en_b = make_pin(b_en_name, machine.Pin.OUT, value=1)
        except Exception:
            pass

        print("Mux scan: threshold={}, settle={}us, adc={}".format(
            self.threshold, self.settle_us, adc_type))

        # Build pad list
        for pad_cfg in pads_config:
            note_id = pad_cfg.get("note", "")
            mux_id = pad_cfg.get("mux", "a").lower()
            channel = pad_cfg.get("channel", 0)

            note_info = find_note(note_id, by_name, by_idx, by_midi)
            if note_info is None:
                print("WARNING: Note {} not in layout".format(note_id))
                continue

            self.pads.append({
                "note": note_info,
                "mux": mux_id,
                "channel": channel,
                "was_active": False,
            })

        print("Configured {} pads ({} on mux A, {} on mux B)".format(
            len(self.pads),
            sum(1 for p in self.pads if p["mux"] == "a"),
            sum(1 for p in self.pads if p["mux"] == "b"),
        ))

    def _set_channel(self, channel):
        for i in range(self.num_select):
            self.select_pins[i].value(1 if (channel & (1 << i)) else 0)

    def _enable_mux(self, mux_id):
        if self.en_a:
            self.en_a.value(0 if mux_id == "a" else 1)
        if self.en_b:
            self.en_b.value(0 if mux_id == "b" else 1)

    def _read_channel(self, mux_id, channel):
        self._enable_mux(mux_id)
        self._set_channel(channel)
        time.sleep_us(self.settle_us)

        if self.ads:
            ch = self.adc_a_ch if mux_id == "a" else self.adc_b_ch
            return self.ads.read_channel(ch)
        else:
            adc = self.native_adc_a if mux_id == "a" else self.native_adc_b
            return adc.read_u16() if adc else 0

    def _raw_to_velocity(self, raw):
        above = raw - self.threshold
        max_range = 65535 - self.threshold
        if max_range <= 0:
            return 100
        velocity = int((above / max_range) * 126) + 1
        return max(1, min(127, velocity))

    def scan(self):
        pressed = []
        released = []

        for pad in self.pads:
            raw = self._read_channel(pad["mux"], pad["channel"])
            is_active = raw > self.threshold

            if is_active and not pad["was_active"]:
                vel = self._raw_to_velocity(raw)
                note_with_vel = dict(pad["note"])
                note_with_vel["velocity"] = vel
                pressed.append(note_with_vel)
            elif not is_active and pad["was_active"]:
                released.append(pad["note"])

            pad["was_active"] = is_active

        # Disable both muxes after scan
        if self.en_a:
            self.en_a.value(1)
        if self.en_b:
            self.en_b.value(1)

        return pressed, released

    @property
    def count(self):
        return len(self.pads)


# ---------------------------------------------------------------------------
# Demo / test modes
# ---------------------------------------------------------------------------

def play_demo(player, notes, tempo_bpm=100):
    """Play through all notes to test audio output."""
    beat = 60.0 / tempo_bpm
    print("\n--- Demo: all {} notes ---".format(len(notes)))

    for note in notes:
        name = "{}{}".format(note["name"], note["octave"])
        midi = note["midi"]
        ring = note.get("ring", "?")
        print("  {} (MIDI {}, {})".format(name, midi, ring))
        player.note_on(midi, velocity=90)
        time.sleep(beat * 0.8)

    time.sleep(1.0)
    player.all_off()
    print("--- Demo complete ---\n")


def play_chord_demo(player, notes):
    """Play some chords to demonstrate polyphony."""
    print("\n--- Chord demo (polyphony test) ---")

    midi_map = {n["midi"]: n for n in notes}

    chords = [
        ("C major", [60, 64, 67, 72]),
        ("F major", [65, 69, 72, 77]),
        ("G major", [67, 71, 74, 79]),
        ("C major (high)", [72, 76, 79, 84]),
    ]

    for name, midi_notes in chords:
        playable = [m for m in midi_notes if m in midi_map]
        if not playable:
            continue

        note_names = [midi_to_display(m) for m in playable]
        print("  {}: {}".format(name, ", ".join(note_names)))

        for m in playable:
            player.note_on(m, velocity=85)
            time.sleep(0.05)

        time.sleep(1.5)
        player.all_off()
        time.sleep(0.3)

    print("--- Chord demo complete ---\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _deep_merge(base, override):
    """Merge override dict into base dict. Sub-dicts are merged, not replaced."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def main():
    print("\n" + "=" * 40)
    print("  rpiPan - Steel Pan for Pico")
    print("  (MicroPython)")
    print("=" * 40)

    # Detect board
    board_id = detect_board()
    print("Board: {}".format(board_id))
    print("Platform: {}".format(sys.platform))
    print("CPU freq: {} MHz".format(machine.freq() // 1_000_000))

    # Load layout and hardware config
    notes, hw_config = load_layout("pan_layout.json")
    if not notes:
        print("No notes loaded. Check pan_layout.json.")
        return

    # Merge board defaults with JSON config (JSON overrides defaults)
    defaults = get_board_defaults(board_id)
    hw_config = _deep_merge(defaults, hw_config)

    print("\nLoaded {} notes from pan_layout.json".format(len(notes)))

    # Display layout by ring
    rings = {}
    for n in notes:
        ring = n.get("ring", "unknown")
        if ring not in rings:
            rings[ring] = []
        rings[ring].append(n)

    for ring_name in ["outer", "central", "inner"]:
        if ring_name in rings:
            names = ["{}{}".format(n["name"], n["octave"]) for n in rings[ring_name]]
            print("  {:8s}: {}".format(ring_name, ", ".join(names)))

    print("  Range: MIDI {}-{} ({}-{})".format(
        notes[0]["midi"], notes[-1]["midi"],
        midi_to_display(notes[0]["midi"]),
        midi_to_display(notes[-1]["midi"]),
    ))

    # Hardware config
    i2s_config = hw_config.get("i2s", {})
    adc_config = hw_config.get("adc", None)
    input_mode = hw_config.get("input_mode", "button")
    led_pin_name = hw_config.get("led_pin", "LED")
    max_voices = hw_config.get("max_voices", 6)
    sample_rate = hw_config.get("sample_rate", 22050)
    sounds_dir = hw_config.get("sounds_dir", "sounds")
    pin_map = hw_config.get("pins", {})

    print("\nAudio: I2S ({} voices, {} Hz, software mixing)".format(
        max_voices, sample_rate))
    print("Input: {}".format(input_mode))

    if max_voices > 6:
        print("NOTE: Software mixing works best with <= 6 voices on RP2040")

    # LED indicator
    led = None
    try:
        led = make_pin(led_pin_name, machine.Pin.OUT, value=0)
    except Exception:
        pass

    # Set up audio engine
    engine = None
    try:
        engine = MixEngine(
            i2s_config=i2s_config,
            max_voices=max_voices,
            sample_rate=sample_rate,
            sounds_dir=sounds_dir,
        )
        loaded = engine.load_all(notes)
        if loaded == 0:
            print("No WAV files found in {}/".format(sounds_dir))
            print("Run install.py to convert and copy samples.")
            engine.deinit()
            engine = None
    except Exception as e:
        print("Audio init error: {}".format(e))
        engine = None

    if engine is None:
        print("Cannot start without WAV files. Exiting.")
        return

    # Start audio thread on core 1
    engine.start()
    print("Audio thread started on core 1")

    # If no input pins/pads configured, run demos
    pads_list = hw_config.get("pads", [])
    if not pin_map and not pads_list:
        print("\nNo input pins in pan_layout.json 'hardware.pins'")
        print("Running demo...")

        if led:
            led.value(1)

        # Give the audio thread a moment to start
        time.sleep(0.1)

        play_demo(engine, notes, tempo_bpm=100)
        time.sleep(0.5)
        play_chord_demo(engine, notes)

        if led:
            led.value(0)

        print("Demo finished. Add 'hardware' config to pan_layout.json.")
        print("For full 29-pad tenor pan, use mux_scan mode:")
        print('  "input_mode": "mux_scan"')

        # Idle blink
        while True:
            if led:
                led.toggle()
            time.sleep(1)

    # Set up inputs
    if input_mode == "mux_scan":
        mux_config = hw_config.get("mux", {})
        pads_config = hw_config.get("pads", [])
        inputs = MuxScanInput(notes, mux_config, pads_config, adc_config)
    elif input_mode == "mux_touch":
        mux_config = hw_config.get("mux", {})
        inputs = MuxTouchInput(pin_map, notes, mux_config, adc_config)
    elif input_mode == "touch":
        print("WARNING: Capacitive touch not available in MicroPython")
        print("  Falling back to button mode")
        inputs = ButtonInput(pin_map, notes)
    else:
        inputs = ButtonInput(pin_map, notes)

    print("Configured {} input pins".format(inputs.count))
    print("\nReady - play!")

    if led:
        led.value(1)

    # Main loop - scan inputs, play/stop notes
    while True:
        pressed, released = inputs.scan()

        for note in pressed:
            name = "{}{}".format(note["name"], note["octave"])
            vel = note.get("velocity", 100)
            print("  ON:  {} ({:.0f} Hz, vel={})".format(name, note["freq"], vel))
            engine.note_on(note["midi"], velocity=vel)

        for note in released:
            name = "{}{}".format(note["name"], note["octave"])
            print("  OFF: {}".format(name))

        time.sleep(0.02)  # 50 Hz scan rate


main()
