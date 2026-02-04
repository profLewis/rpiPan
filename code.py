"""
rpiPan - Steel Pan instrument for Raspberry Pi Pico (CircuitPython)

Reads pan_layout.json to configure note layout, plays WAV samples with
polyphonic mixing via audiomixer, responds to touch or button inputs.
Supports velocity-sensitive playback via analog multiplexer readings.

Hardware:
    - Raspberry Pi Pico (RP2040)
    - Audio output on GP18 (configurable PWM audio)
    - Speaker/amplifier connected to audio pin
    - Touch pads or buttons on configurable GPIO pins
    - Optional: analog multiplexer (e.g. CD74HC4067) for velocity sensing

Input modes:
    - "button"    : digital GPIO pins, fixed velocity
    - "touch"     : capacitive touch (touchio), fixed velocity
    - "mux_touch" : digital trigger + analog velocity via multiplexer
    - "mux_scan"  : pure analog scanning (2 muxes, no digital pins needed)

Setup:
    1. Install CircuitPython on the Pico
    2. Copy this file as code.py to CIRCUITPY drive
    3. Copy pan_layout.json to CIRCUITPY drive
    4. Copy sounds/ directory with WAV files to CIRCUITPY drive
       (WAV files: 16-bit signed, mono, 22050 Hz — use install.py to convert)

The sounds/ directory should contain files named like the panipuri project:
    C4.wav, Cs4.wav, D4.wav, Ds4.wav, E4.wav, F4.wav, Fs4.wav, ...
    (sharps use lowercase 's': Cs = C#, Fs = F#, etc.)
"""

import json
import time
import board
import digitalio

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

# For building WAV filenames (matches panipuri sounds/ convention)
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
    """Convert MIDI note to WAV filename (e.g. 60 -> 'C4.wav', 66 -> 'Fs4.wav')."""
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
        print("ERROR: pan_layout.json not found on CIRCUITPY drive")
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
# Polyphonic WAV player using audiomixer
# ---------------------------------------------------------------------------

class WavPlayer:
    """Polyphonic WAV sample player using CircuitPython audiomixer.

    Loads WAV files from sounds/ directory and plays them through
    an audiomixer.Mixer with round-robin voice allocation, allowing
    multiple notes to sound simultaneously.
    """

    def __init__(self, audio_pin="GP18", max_voices=8,
                 sample_rate=22050, sounds_dir="sounds"):
        import audiopwmio
        import audiomixer

        self.sounds_dir = sounds_dir
        self.max_voices = max_voices
        self.sample_rate = sample_rate

        # Set up PWM audio output
        pin = getattr(board, audio_pin, None)
        if pin is None:
            raise ValueError("Audio pin {} not found".format(audio_pin))

        self.audio = audiopwmio.PWMAudioOut(pin)

        # Create mixer with multiple voices
        self.mixer = audiomixer.Mixer(
            voice_count=max_voices,
            sample_rate=sample_rate,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )

        # Start the mixer playing (it runs continuously, voices are added/removed)
        self.audio.play(self.mixer)

        # Voice tracking: which MIDI note is on each voice
        self._voice_note = [None] * max_voices
        self._next_voice = 0

        # Cache of loaded WaveFile objects: midi_note -> open file + WaveFile
        # We keep file handles open so WaveFile can stream from them
        self._wav_cache = {}
        self._file_cache = {}

    def load_note(self, midi_note, filename):
        """Pre-load a WAV file for a note. Returns True if successful."""
        import audiocore

        path = "{}/{}".format(self.sounds_dir, filename)
        try:
            f = open(path, "rb")
            wav = audiocore.WaveFile(f)
            self._wav_cache[midi_note] = wav
            self._file_cache[midi_note] = f
            return True
        except OSError:
            return False
        except Exception as e:
            print("  Load error {}: {}".format(filename, e))
            return False

    def load_all(self, notes):
        """Load WAV files for all notes in the layout."""
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

    def _alloc_voice(self):
        """Allocate a mixer voice using round-robin."""
        voice = self._next_voice
        self._next_voice = (self._next_voice + 1) % self.max_voices
        return voice

    def _find_voice(self, midi_note):
        """Find which voice is playing a given note, or None."""
        for i, note in enumerate(self._voice_note):
            if note == midi_note:
                return i
        return None

    def note_on(self, midi_note, velocity=100):
        """Start playing a note. Allocates a mixer voice and plays the WAV.

        If the note is already playing, restarts it.
        If all voices are in use, steals the oldest (round-robin).
        """
        wav = self._wav_cache.get(midi_note)
        if wav is None:
            return

        # If this note is already playing, stop it first
        existing = self._find_voice(midi_note)
        if existing is not None:
            self.mixer.voice[existing].stop()
            self._voice_note[existing] = None

        # Allocate a voice
        voice_idx = self._alloc_voice()

        # Stop whatever was on this voice
        self.mixer.voice[voice_idx].stop()

        # Set volume based on velocity (curve for natural dynamics)
        vol = (velocity / 127.0) ** 0.7
        self.mixer.voice[voice_idx].level = vol

        # Rewind the WAV to the start and play
        # We need to re-open the file since WaveFile doesn't support seeking
        # after playback in CircuitPython
        import audiocore
        midi = midi_note
        if midi in self._file_cache:
            try:
                self._file_cache[midi].seek(0)
                wav = audiocore.WaveFile(self._file_cache[midi])
                self._wav_cache[midi] = wav
            except Exception:
                return

        self.mixer.voice[voice_idx].play(wav)
        self._voice_note[voice_idx] = midi_note

    def note_off(self, midi_note):
        """Stop a specific note (with fadeout-like behavior).

        Steel pan notes naturally decay, so this is optional.
        Call this to cut a note short.
        """
        voice_idx = self._find_voice(midi_note)
        if voice_idx is not None:
            # Fade out by reducing level (instant stop sounds harsh)
            self.mixer.voice[voice_idx].level = 0.0
            self.mixer.voice[voice_idx].stop()
            self._voice_note[voice_idx] = None

    def all_off(self):
        """Stop all voices."""
        for i in range(self.max_voices):
            self.mixer.voice[i].stop()
            self._voice_note[i] = None

    def deinit(self):
        """Clean up audio resources."""
        self.all_off()
        self.audio.stop()
        self.audio.deinit()
        for f in self._file_cache.values():
            f.close()
        self._file_cache.clear()
        self._wav_cache.clear()


# ---------------------------------------------------------------------------
# Fallback: PWM tone player (no WAV files needed)
# ---------------------------------------------------------------------------

class TonePlayer:
    """Simple monophonic square-wave tone generator via PWM.

    Used as fallback when no WAV files are available.
    """

    def __init__(self, pin_name="GP18"):
        import pwmio
        self.pwmio = pwmio
        self.pin_name = pin_name
        self.pin = getattr(board, pin_name, None)
        self.pwm = None

    def note_on(self, midi_note, velocity=100):
        freq = int(midi_to_freq(midi_note))
        if self.pin is None or freq < 20 or freq > 20000:
            return
        self.note_off(midi_note)
        try:
            duty = int(32768 * (velocity / 127.0) ** 0.7)
            self.pwm = self.pwmio.PWMOut(
                self.pin, frequency=freq, duty_cycle=duty, variable_frequency=True
            )
        except Exception as e:
            print("Tone error: {}".format(e))

    def note_off(self, midi_note):
        if self.pwm is not None:
            try:
                self.pwm.deinit()
            except Exception:
                pass
            self.pwm = None

    def all_off(self):
        self.note_off(0)

    def load_all(self, notes):
        print("Tone mode (no WAV files)")
        return 0

    def deinit(self):
        self.all_off()


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
            bp = getattr(board, pin_name, None)
            if bp is None:
                print("WARNING: Pin {} not found".format(pin_name))
                continue

            note_info = find_note(note_id, by_name, by_idx, by_midi)
            if note_info is None:
                print("WARNING: Note {} not in layout".format(note_id))
                continue

            try:
                dio = digitalio.DigitalInOut(bp)
                dio.direction = digitalio.Direction.INPUT
                dio.pull = digitalio.Pull.UP
                self.buttons.append({
                    "pin": dio,
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
            is_pressed = not btn["pin"].value
            if is_pressed and not btn["was_pressed"]:
                pressed.append(btn["note"])
            elif not is_pressed and btn["was_pressed"]:
                released.append(btn["note"])
            btn["was_pressed"] = is_pressed
        return pressed, released

    @property
    def count(self):
        return len(self.buttons)


class TouchInput:
    """Reads GPIO pins as capacitive touch inputs."""

    def __init__(self, pin_map, notes):
        self.pads = []
        by_name, by_idx, by_midi = build_note_lookup(notes)

        try:
            import touchio
        except ImportError:
            print("WARNING: touchio unavailable")
            return

        for pin_name, note_id in pin_map.items():
            bp = getattr(board, pin_name, None)
            if bp is None:
                print("WARNING: Pin {} not found".format(pin_name))
                continue

            note_info = find_note(note_id, by_name, by_idx, by_midi)
            if note_info is None:
                print("WARNING: Note {} not in layout".format(note_id))
                continue

            try:
                tp = touchio.TouchIn(bp)
                self.pads.append({
                    "pad": tp,
                    "note": note_info,
                    "was_touched": False,
                })
            except Exception as e:
                print("WARNING: Touch {} failed: {}".format(pin_name, e))

    def scan(self):
        """Returns (pressed_notes, released_notes) lists."""
        pressed = []
        released = []
        for pad in self.pads:
            is_touched = pad["pad"].value
            if is_touched and not pad["was_touched"]:
                pressed.append(pad["note"])
            elif not is_touched and pad["was_touched"]:
                released.append(pad["note"])
            pad["was_touched"] = is_touched
        return pressed, released

    @property
    def count(self):
        return len(self.pads)


class MuxTouchInput:
    """Digital touch trigger + analog velocity via multiplexer.

    Each pad has a digital GPIO pin for touch detection and a channel
    on an analog multiplexer (e.g. CD74HC4067) for reading strike
    intensity. The mux select pins choose which channel to read;
    the analog pin returns a 0-3.3V signal proportional to force.

    Config in pan_layout.json:
        "hardware": {
            "input_mode": "mux_touch",
            "mux": {
                "analog_pin": "GP26",
                "select_pins": ["GP10", "GP11", "GP12", "GP13"]
            },
            "pins": {
                "GP0": {"note": "C4", "mux_channel": 0},
                "GP1": {"note": "D4", "mux_channel": 1}
            }
        }
    """

    def __init__(self, pin_map, notes, mux_config):
        import analogio

        self.pads = []
        by_name, by_idx, by_midi = build_note_lookup(notes)

        # Set up mux analog input
        adc_pin_name = mux_config.get("analog_pin", "GP26")
        adc_pin = getattr(board, adc_pin_name, None)
        if adc_pin is None:
            print("ERROR: ADC pin {} not found".format(adc_pin_name))
            return
        self.adc = analogio.AnalogIn(adc_pin)

        # Set up mux select pins as digital outputs
        self.select_pins = []
        for sp_name in mux_config.get("select_pins", []):
            sp = getattr(board, sp_name, None)
            if sp is None:
                print("WARNING: Mux select pin {} not found".format(sp_name))
                continue
            dio = digitalio.DigitalInOut(sp)
            dio.direction = digitalio.Direction.OUTPUT
            dio.value = False
            self.select_pins.append(dio)

        self.num_select = len(self.select_pins)
        print("Mux: {} on {}, {} select pins".format(
            adc_pin_name, ", ".join(mux_config.get("select_pins", [])),
            self.num_select))

        # Set up per-pad digital trigger + mux channel
        for pin_name, pad_cfg in pin_map.items():
            # Support both dict and string pin configs
            if isinstance(pad_cfg, str):
                note_id = pad_cfg
                mux_ch = None
            else:
                note_id = pad_cfg.get("note", "")
                mux_ch = pad_cfg.get("mux_channel")

            bp = getattr(board, pin_name, None)
            if bp is None:
                print("WARNING: Pin {} not found".format(pin_name))
                continue

            note_info = find_note(note_id, by_name, by_idx, by_midi)
            if note_info is None:
                print("WARNING: Note {} not in layout".format(note_id))
                continue

            try:
                dio = digitalio.DigitalInOut(bp)
                dio.direction = digitalio.Direction.INPUT
                dio.pull = digitalio.Pull.UP
                self.pads.append({
                    "pin": dio,
                    "note": note_info,
                    "mux_channel": mux_ch,
                    "was_pressed": False,
                })
            except Exception as e:
                print("WARNING: {} init failed: {}".format(pin_name, e))

    def _set_mux_channel(self, channel):
        """Set mux select pins to address a channel (binary encoding)."""
        for i in range(self.num_select):
            self.select_pins[i].value = bool(channel & (1 << i))

    def _read_velocity(self, channel):
        """Read analog value from a mux channel and map to velocity 1-127."""
        if channel is None or self.num_select == 0:
            return 100  # default velocity if no mux channel assigned

        self._set_mux_channel(channel)
        # Small settle time for mux switching
        time.sleep(0.001)
        raw = self.adc.value  # 0-65535 (16-bit, 0-3.3V)

        # Linear map: 0V -> velocity 1, 3.3V -> velocity 127
        velocity = int((raw / 65535.0) * 126) + 1
        return max(1, min(127, velocity))

    def scan(self):
        """Scan digital pins; read analog velocity for new presses.

        Returns (pressed_notes, released_notes). Each pressed note dict
        has a "velocity" key set from the analog reading.
        """
        pressed = []
        released = []

        for pad in self.pads:
            is_pressed = not pad["pin"].value  # active low
            if is_pressed and not pad["was_pressed"]:
                vel = self._read_velocity(pad["mux_channel"])
                # Attach velocity to a copy so we don't mutate the note dict
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
    """Pure analog scanning via dual multiplexers — no digital pins needed.

    Scans all pads through 2x CD74HC4067 muxes sharing select pins.
    Each mux has its own ADC pin and enable pin. Touch detection uses
    a configurable voltage threshold; strike intensity above the
    threshold maps to velocity.

    This mode supports up to 32 pads (16 per mux) using only 9 Pico
    GPIO pins total, making it ideal for a full 29-note tenor pan.

    Pico pin usage:
        GP10-GP13 : mux select S0-S3 (shared, 4 pins)
        GP26      : ADC for mux A (channels 0-15)
        GP27      : ADC for mux B (channels 0-15)
        GP14      : mux A enable (active low)
        GP15      : mux B enable (active low)
        GP18      : audio output

    Config in pan_layout.json:
        "hardware": {
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
                {"note": "D4", "mux": "a", "channel": 1},
                ...
            ]
        }
    """

    def __init__(self, notes, mux_config, pads_config):
        import analogio

        self.pads = []
        by_name, by_idx, by_midi = build_note_lookup(notes)

        # Threshold for touch detection (0-65535, ~3000 ≈ 0.15V)
        self.threshold = mux_config.get("threshold", 3000)
        # Settle time in microseconds after switching mux channel
        self.settle_us = mux_config.get("settle_us", 100)

        # Set up shared mux select pins
        self.select_pins = []
        for sp_name in mux_config.get("select_pins", []):
            sp = getattr(board, sp_name, None)
            if sp is None:
                print("WARNING: Select pin {} not found".format(sp_name))
                continue
            dio = digitalio.DigitalInOut(sp)
            dio.direction = digitalio.Direction.OUTPUT
            dio.value = False
            self.select_pins.append(dio)
        self.num_select = len(self.select_pins)

        # Set up mux A
        mux_a_cfg = mux_config.get("mux_a", {})
        self.adc_a = None
        self.en_a = None
        a_pin = getattr(board, mux_a_cfg.get("analog_pin", "GP26"), None)
        if a_pin:
            self.adc_a = analogio.AnalogIn(a_pin)
        a_en = getattr(board, mux_a_cfg.get("enable_pin", "GP14"), None)
        if a_en:
            self.en_a = digitalio.DigitalInOut(a_en)
            self.en_a.direction = digitalio.Direction.OUTPUT
            self.en_a.value = True  # disabled (active low)

        # Set up mux B
        mux_b_cfg = mux_config.get("mux_b", {})
        self.adc_b = None
        self.en_b = None
        b_pin = getattr(board, mux_b_cfg.get("analog_pin", "GP27"), None)
        if b_pin:
            self.adc_b = analogio.AnalogIn(b_pin)
        b_en = getattr(board, mux_b_cfg.get("enable_pin", "GP15"), None)
        if b_en:
            self.en_b = digitalio.DigitalInOut(b_en)
            self.en_b.direction = digitalio.Direction.OUTPUT
            self.en_b.value = True  # disabled

        mux_a_name = mux_a_cfg.get("analog_pin", "GP26")
        mux_b_name = mux_b_cfg.get("analog_pin", "GP27")
        print("Mux scan: A={}, B={}, threshold={}, settle={}us".format(
            mux_a_name, mux_b_name, self.threshold, self.settle_us))

        # Build pad list from pads config
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
        """Set mux select pins to address a channel."""
        for i in range(self.num_select):
            self.select_pins[i].value = bool(channel & (1 << i))

    def _enable_mux(self, mux_id):
        """Enable one mux, disable the other."""
        if self.en_a:
            self.en_a.value = (mux_id != "a")  # active low
        if self.en_b:
            self.en_b.value = (mux_id != "b")

    def _read_channel(self, mux_id, channel):
        """Read raw ADC value from a specific mux and channel."""
        self._enable_mux(mux_id)
        self._set_channel(channel)
        # Settle time (use sleep for microsecond-range delays)
        time.sleep(self.settle_us / 1_000_000)

        if mux_id == "a" and self.adc_a:
            return self.adc_a.value
        elif mux_id == "b" and self.adc_b:
            return self.adc_b.value
        return 0

    def _raw_to_velocity(self, raw):
        """Map raw ADC value above threshold to velocity 1-127."""
        # Scale the range from threshold..65535 to 1..127
        above = raw - self.threshold
        max_range = 65535 - self.threshold
        if max_range <= 0:
            return 100
        velocity = int((above / max_range) * 126) + 1
        return max(1, min(127, velocity))

    def scan(self):
        """Scan all pads through both muxes.

        Returns (pressed_notes, released_notes). Each pressed note dict
        has a "velocity" key derived from the analog reading.
        """
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
            self.en_a.value = True
        if self.en_b:
            self.en_b.value = True

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
        # Don't explicitly stop - let notes overlap and decay naturally
        # (this demonstrates polyphony)

    # Wait for last note to decay
    time.sleep(1.0)
    player.all_off()
    print("--- Demo complete ---\n")


def play_chord_demo(player, notes):
    """Play some chords to demonstrate polyphony."""
    print("\n--- Chord demo (polyphony test) ---")

    # Build MIDI lookup
    midi_map = {n["midi"]: n for n in notes}

    # C major chord: C4, E4, G4, C5
    chords = [
        ("C major", [60, 64, 67, 72]),
        ("F major", [65, 69, 72, 77]),
        ("G major", [67, 71, 74, 79]),
        ("C major (high)", [72, 76, 79, 84]),
    ]

    for name, midi_notes in chords:
        # Only play notes that exist in our layout
        playable = [m for m in midi_notes if m in midi_map]
        if not playable:
            continue

        note_names = [midi_to_display(m) for m in playable]
        print("  {}: {}".format(name, ", ".join(note_names)))

        # Play all notes in the chord simultaneously
        for m in playable:
            player.note_on(m, velocity=85)
            time.sleep(0.05)  # tiny stagger for realism

        time.sleep(1.5)
        player.all_off()
        time.sleep(0.3)

    print("--- Chord demo complete ---\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 40)
    print("  rpiPan - Steel Pan for Pico")
    print("=" * 40)

    # Load layout and hardware config
    notes, hw_config = load_layout("pan_layout.json")
    if not notes:
        print("No notes loaded. Check pan_layout.json.")
        return

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

    # Hardware config with defaults
    audio_pin = hw_config.get("audio_pin", "GP18")
    input_mode = hw_config.get("input_mode", "button")
    led_pin_name = hw_config.get("led_pin", "LED")
    max_voices = hw_config.get("max_voices", 8)
    sample_rate = hw_config.get("sample_rate", 22050)
    sounds_dir = hw_config.get("sounds_dir", "sounds")
    pin_map = hw_config.get("pins", {})

    print("\nAudio: {} ({} voices, {} Hz)".format(audio_pin, max_voices, sample_rate))
    print("Input: {}".format(input_mode))

    # LED indicator
    led = None
    lp = getattr(board, led_pin_name, None)
    if lp:
        try:
            led = digitalio.DigitalInOut(lp)
            led.direction = digitalio.Direction.OUTPUT
        except Exception:
            pass

    # Try to set up polyphonic WAV player, fall back to tone player
    player = None
    try:
        player = WavPlayer(
            audio_pin=audio_pin,
            max_voices=max_voices,
            sample_rate=sample_rate,
            sounds_dir=sounds_dir,
        )
        loaded = player.load_all(notes)
        if loaded == 0:
            print("No WAV files found in {}/".format(sounds_dir))
            print("Falling back to PWM tone mode")
            player.deinit()
            player = None
    except ImportError as e:
        print("audiomixer not available: {}".format(e))
        print("Falling back to PWM tone mode")
    except Exception as e:
        print("Audio init error: {}".format(e))
        print("Falling back to PWM tone mode")

    if player is None:
        player = TonePlayer(audio_pin)
        player.load_all(notes)

    # If no input pins/pads configured, run demos
    pads_list = hw_config.get("pads", [])
    if not pin_map and not pads_list:
        print("\nNo input pins in pan_layout.json 'hardware.pins'")
        print("Running demo...")
        print("(Configure pins to map GPIO -> notes for interactive play)")

        if led:
            led.value = True

        play_demo(player, notes, tempo_bpm=100)
        time.sleep(0.5)
        play_chord_demo(player, notes)

        if led:
            led.value = False

        print("Demo finished. Add 'hardware' config to pan_layout.json.")
        print("For full 29-pad tenor pan, use mux_scan mode:")
        print('  "input_mode": "mux_scan"')
        print("  See pan_layout.json for complete configuration.")

        # Idle blink
        while True:
            if led:
                led.value = not led.value
            time.sleep(1)

    # Set up inputs
    if input_mode == "mux_scan":
        mux_config = hw_config.get("mux", {})
        pads_config = hw_config.get("pads", [])
        inputs = MuxScanInput(notes, mux_config, pads_config)
    elif input_mode == "mux_touch":
        mux_config = hw_config.get("mux", {})
        inputs = MuxTouchInput(pin_map, notes, mux_config)
    elif input_mode == "touch":
        inputs = TouchInput(pin_map, notes)
    else:
        inputs = ButtonInput(pin_map, notes)

    print("Configured {} input pins".format(inputs.count))
    print("\nReady - play!")

    if led:
        led.value = True

    # Main loop - scan inputs, play/stop notes
    while True:
        pressed, released = inputs.scan()

        for note in pressed:
            name = "{}{}".format(note["name"], note["octave"])
            vel = note.get("velocity", 100)
            print("  ON:  {} ({:.0f} Hz, vel={})".format(name, note["freq"], vel))
            player.note_on(note["midi"], velocity=vel)

        for note in released:
            name = "{}{}".format(note["name"], note["octave"])
            print("  OFF: {}".format(name))
            # Don't stop notes on release - let them decay naturally
            # like a real steel pan. Uncomment below to cut notes short:
            # player.note_off(note["midi"])

        time.sleep(0.02)  # 50 Hz scan rate


main()
