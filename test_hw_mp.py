"""
test_hw_mp.py - Hardware diagnostic for rpiPan (runs on Pico under MicroPython)

Copy this file to the Pico as test_hw.py (via Thonny or mpremote), then
run it from Thonny (F5) or from the REPL:
    exec(open("test_hw.py").read())

Tests:
    1. Board detection
    2. I2S audio output (test tones via Waveshare Pico-Audio)
    3. ADS1115 I2C ADC (voltage readings on all 4 channels)
    4. HW-178 mux scanning (all 29 pads, raw voltages)
    5. GPIO pin state survey
    6. WAV file check and playback

Results are printed to the serial console (Thonny Shell or mpremote).
"""

import time
import machine
import math
import array
import struct
import sys
import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pin_num(name):
    """Convert CircuitPython-style pin name to integer. 'GP10' -> 10."""
    if name == "LED":
        return 25
    if name.startswith("GP"):
        return int(name[2:])
    return int(name)


def divider(title):
    print("\n" + "=" * 50)
    print("  {}".format(title))
    print("=" * 50)


def passed(msg):
    print("  [PASS] {}".format(msg))


def failed(msg):
    print("  [FAIL] {}".format(msg))


def info(msg):
    print("  [INFO] {}".format(msg))


# ---------------------------------------------------------------------------
# Inline ADS1115 driver (same as in main_mp.py)
# ---------------------------------------------------------------------------

class ADS1115:
    """Minimal ADS1115 driver for single-ended reads."""

    _CONV_REG = 0x00
    _CONF_REG = 0x01
    _MUX = [0x4000, 0x5000, 0x6000, 0x7000]
    _BASE_CONFIG = 0x8100 | 0x0200 | 0x00E0 | 0x0003

    def __init__(self, i2c, addr=0x48):
        self.i2c = i2c
        self.addr = addr
        self._buf = bytearray(2)

    def read_channel(self, channel):
        """Read single-ended channel (0-3). Returns 0-65535."""
        config = self._BASE_CONFIG | self._MUX[channel]
        self._buf[0] = (config >> 8) & 0xFF
        self._buf[1] = config & 0xFF
        self.i2c.writeto_mem(self.addr, self._CONF_REG, self._buf)
        time.sleep_ms(2)
        for _ in range(10):
            self.i2c.readfrom_mem_into(self.addr, self._CONF_REG, self._buf)
            if self._buf[0] & 0x80:
                break
            time.sleep_us(200)
        self.i2c.readfrom_mem_into(self.addr, self._CONV_REG, self._buf)
        raw = (self._buf[0] << 8) | self._buf[1]
        if raw >= 0x8000:
            raw -= 0x10000
        return raw + 32768

    def read_voltage(self, channel):
        """Read channel and convert to voltage (assuming +/-4.096V gain)."""
        raw_unsigned = self.read_channel(channel)
        raw_signed = raw_unsigned - 32768
        return raw_signed * 4.096 / 32768


# ---------------------------------------------------------------------------
# 1. Board detection
# ---------------------------------------------------------------------------

def test_board():
    divider("Board Detection")

    print("  sys.platform = {}".format(sys.platform))
    print("  sys.implementation = {}".format(sys.implementation))
    print("  CPU freq = {} MHz".format(machine.freq() // 1_000_000))

    # Check for Pico W
    is_pico_w = False
    try:
        import network
        is_pico_w = True
        info("WiFi module detected (Pico W)")
    except ImportError:
        info("No WiFi module (standard Pico)")

    # Check LED
    try:
        led = machine.Pin(25, machine.Pin.OUT)
        led.value(1)
        passed("LED on (GP25)")
        time.sleep(0.3)
        led.value(0)
    except Exception as e:
        failed("LED: {}".format(e))

    board_type = "pico_w" if is_pico_w else "pico"
    return board_type


# ---------------------------------------------------------------------------
# 2. I2S audio test
# ---------------------------------------------------------------------------

def test_i2s_audio():
    divider("I2S Audio Output")

    info("I2S pins: DATA=GP26, BCK=GP27, LRCK=GP28")

    try:
        i2s = machine.I2S(
            0,
            sck=machine.Pin(27),
            ws=machine.Pin(28),
            sd=machine.Pin(26),
            mode=machine.I2S.TX,
            bits=16,
            format=machine.I2S.MONO,
            rate=22050,
            ibuf=8192,
        )
        passed("I2S initialized")
    except Exception as e:
        failed("I2S init: {}".format(e))
        return False

    sample_rate = 22050
    duration_ms = 400
    n_samples = int(sample_rate * duration_ms / 1000)

    test_freqs = [
        ("C4  (262 Hz)", 262),
        ("E4  (330 Hz)", 330),
        ("G4  (392 Hz)", 392),
        ("C5  (523 Hz)", 523),
        ("A4  (440 Hz)", 440),
        ("silence",      0),
    ]

    for name, freq in test_freqs:
        if freq == 0:
            buf = array.array("h", [0] * 1000)
            out = bytearray(len(buf) * 2)
            struct.pack_into("<{}h".format(len(buf)), out, 0, *buf)
            i2s.write(out)
            time.sleep(0.2)
            info("{}: OK (no sound expected)".format(name))
            continue

        # Generate sine wave
        buf = array.array("h", [0] * n_samples)
        period = sample_rate / freq
        fade_samples = int(sample_rate * 0.02)
        for i in range(n_samples):
            env = 1.0
            if i < fade_samples:
                env = i / fade_samples
            elif i > n_samples - fade_samples:
                env = (n_samples - i) / fade_samples
            buf[i] = int(math.sin(2.0 * math.pi * i / period) * 28000 * env)

        out = bytearray(n_samples * 2)
        struct.pack_into("<{}h".format(n_samples), out, 0, *buf)

        try:
            i2s.write(out)
            passed("{}: playing".format(name))
            time.sleep(0.1)
        except Exception as e:
            failed("{}: {}".format(name, e))

    # Polyphony test: mix 4 tones
    info("Polyphony test: C major chord (software mix)...")
    chord_freqs = [262, 330, 392, 523]
    mix_buf = array.array("h", [0] * n_samples)

    for freq in chord_freqs:
        period = sample_rate / freq
        fade_samples = int(sample_rate * 0.02)
        for i in range(n_samples):
            env = 1.0
            if i < fade_samples:
                env = i / fade_samples
            elif i > n_samples - fade_samples:
                env = (n_samples - i) / fade_samples
            s = int(math.sin(2.0 * math.pi * i / period) * 7000 * env)
            mix_buf[i] = max(-32768, min(32767, mix_buf[i] + s))

    out = bytearray(n_samples * 2)
    struct.pack_into("<{}h".format(n_samples), out, 0, *mix_buf)
    i2s.write(out)
    passed("Chord playing (4 tones mixed)")
    time.sleep(0.3)

    # Sweep test
    info("Frequency sweep: 200-2000 Hz...")
    sweep_duration = 1.5
    sweep_samples = int(sample_rate * sweep_duration)
    chunk_size = 2048
    sweep_buf = array.array("h", [0] * chunk_size)
    sweep_out = bytearray(chunk_size * 2)
    freq_start = 200
    freq_end = 2000

    total_chunks = sweep_samples // chunk_size
    for c in range(total_chunks):
        t_start = c * chunk_size / sample_rate
        for i in range(chunk_size):
            t = t_start + i / sample_rate
            frac = t / sweep_duration
            freq = freq_start + (freq_end - freq_start) * frac
            sweep_buf[i] = int(math.sin(2.0 * math.pi * freq * t) * 24000)
        struct.pack_into("<{}h".format(chunk_size), sweep_out, 0, *sweep_buf)
        i2s.write(sweep_out)

    passed("Sweep complete")

    i2s.deinit()
    passed("I2S audio test complete")
    return True


# ---------------------------------------------------------------------------
# 3. ADS1115 I2C ADC test
# ---------------------------------------------------------------------------

def test_ads1115():
    divider("ADS1115 I2C ADC")

    try:
        i2c = machine.I2C(0, scl=machine.Pin(5), sda=machine.Pin(4), freq=400000)
        passed("I2C bus initialized (SDA=GP4, SCL=GP5)")
    except Exception as e:
        failed("I2C init: {}".format(e))
        return False

    # Scan I2C bus
    devices = i2c.scan()
    if devices:
        addrs = ["0x{:02X}".format(d) for d in devices]
        info("I2C devices found: {}".format(", ".join(addrs)))
        if 0x48 in devices:
            passed("ADS1115 detected at 0x48")
        else:
            info("ADS1115 not at default address 0x48")
    else:
        failed("No I2C devices found. Check wiring: SDA=GP4, SCL=GP5, VCC=3.3V")
        return False

    # Read channels
    try:
        ads = ADS1115(i2c)
        passed("ADS1115 driver initialized")
    except Exception as e:
        failed("ADS1115 driver: {}".format(e))
        return False

    channel_names = ["A0 (Mux A SIG)", "A1 (Mux B SIG)", "A2 (free)", "A3 (free)"]

    print("\n  Channel readings (10 samples averaged):")
    print("  {:20s}  {:>8s}  {:>10s}".format("Channel", "Raw", "Voltage"))
    print("  " + "-" * 42)

    for ch_idx, ch_name in enumerate(channel_names):
        try:
            raw_sum = 0
            volt_sum = 0.0
            n = 10
            for _ in range(n):
                raw_sum += ads.read_channel(ch_idx)
                volt_sum += ads.read_voltage(ch_idx)
                time.sleep_ms(2)
            raw_avg = raw_sum // n
            volt_avg = volt_sum / n
            print("  {:20s}  {:>8d}  {:>8.3f} V".format(ch_name, raw_avg, volt_avg))
        except Exception as e:
            print("  {:20s}  ERROR: {}".format(ch_name, e))

    passed("ADS1115 channel read complete")
    return True


# ---------------------------------------------------------------------------
# 4. Mux scanning test
# ---------------------------------------------------------------------------

def test_mux_scan():
    divider("HW-178 Mux Scan (29 pads)")

    # Set up select pins
    select_names = ["GP10", "GP11", "GP12", "GP13"]
    select_pins = []
    for name in select_names:
        n = pin_num(name)
        pin = machine.Pin(n, machine.Pin.OUT, value=0)
        select_pins.append(pin)
    passed("Select pins: {}".format(", ".join(select_names)))

    # Set up enable pins
    en_a = machine.Pin(14, machine.Pin.OUT, value=1)
    en_b = machine.Pin(15, machine.Pin.OUT, value=1)
    passed("Enable pins: GP14 (mux A), GP15 (mux B)")

    # Set up ADS1115
    try:
        i2c = machine.I2C(0, scl=machine.Pin(5), sda=machine.Pin(4), freq=400000)
        ads = ADS1115(i2c)
    except Exception as e:
        failed("ADS1115 init for mux scan: {}".format(e))
        return False

    def set_channel(channel):
        for i in range(4):
            select_pins[i].value(1 if (channel & (1 << i)) else 0)

    def enable_mux(mux_id):
        en_a.value(0 if mux_id == "a" else 1)
        en_b.value(0 if mux_id == "b" else 1)

    def read_mux(mux_id, channel):
        enable_mux(mux_id)
        set_channel(channel)
        time.sleep_ms(1)
        ch = 0 if mux_id == "a" else 1
        raw = ads.read_channel(ch)
        voltage = ads.read_voltage(ch)
        return raw, voltage

    pads = [
        ("C4",  "a", 0),  ("C#4", "a", 1),  ("D4",  "a", 2),  ("Eb4", "a", 3),
        ("E4",  "a", 4),  ("F4",  "a", 5),  ("F#4", "a", 6),  ("G4",  "a", 7),
        ("Ab4", "a", 8),  ("A4",  "a", 9),  ("Bb4", "a", 10), ("B4",  "a", 11),
        ("C5",  "a", 12), ("C#5", "a", 13), ("D5",  "a", 14), ("Eb5", "a", 15),
        ("E5",  "b", 0),  ("F5",  "b", 1),  ("F#5", "b", 2),  ("G5",  "b", 3),
        ("Ab5", "b", 4),  ("A5",  "b", 5),  ("Bb5", "b", 6),  ("B5",  "b", 7),
        ("C6",  "b", 8),  ("C#6", "b", 9),  ("D6",  "b", 10), ("Eb6", "b", 11),
        ("E6",  "b", 12),
    ]

    print("\n  {:>3s}  {:>4s}  {:>3s}  {:>3s}  {:>8s}  {:>8s}  {:>8s}".format(
        "#", "Note", "Mux", "Ch", "Raw", "Voltage", "Status"))
    print("  " + "-" * 50)

    threshold = 3000
    active_count = 0

    for i, (note, mux_id, channel) in enumerate(pads):
        raw, voltage = read_mux(mux_id, channel)
        status = "ACTIVE" if raw > threshold else "idle"
        if raw > threshold:
            active_count += 1
        print("  {:>3d}  {:>4s}  {:>3s}  {:>3d}  {:>8d}  {:>6.3f} V  {:>8s}".format(
            i, note, mux_id.upper(), channel, raw, voltage, status))

    # Disable muxes
    en_a.value(1)
    en_b.value(1)

    print("\n  Active pads (above threshold {}): {}".format(threshold, active_count))
    if active_count == 0:
        info("No pads active (expected if nothing is being pressed)")
    elif active_count > 5:
        info("Many pads active -- check for noise or floating inputs")

    # Unused channels on mux B
    print("\n  Unused mux B channels:")
    for ch in [13, 14, 15]:
        raw, voltage = read_mux("b", ch)
        print("    B/C{}: raw={}, voltage={:.3f}V".format(ch, raw, voltage))

    en_a.value(1)
    en_b.value(1)

    passed("Mux scan complete")
    return True


# ---------------------------------------------------------------------------
# 5. GPIO pin survey
# ---------------------------------------------------------------------------

def test_gpio_survey():
    divider("GPIO Pin Survey")

    used_pins = {
        4: "I2C SDA (ADS1115)",
        5: "I2C SCL (ADS1115)",
        10: "Mux S0",
        11: "Mux S1",
        12: "Mux S2",
        13: "Mux S3",
        14: "Mux A EN",
        15: "Mux B EN",
        25: "LED",
        26: "I2S DATA (Pico-Audio)",
        27: "I2S BCK (Pico-Audio)",
        28: "I2S LRCK (Pico-Audio)",
    }

    print("\n  {:>5s}  {:>7s}  {:s}".format("Pin", "State", "Assignment"))
    print("  " + "-" * 45)

    all_pins = list(range(29))
    free_pins = []

    for n in all_pins:
        name = "GP{}".format(n)
        assignment = used_pins.get(n, "(free)")
        state = "?"

        if n in (26, 27, 28, 4, 5):
            state = "in use"
        elif n in used_pins:
            state = "config"
        else:
            try:
                pin = machine.Pin(n, machine.Pin.IN, machine.Pin.PULL_UP)
                time.sleep_ms(1)
                val = pin.value()
                state = "HIGH" if val else "LOW "
            except Exception:
                state = "error"

        if n not in used_pins:
            free_pins.append(name)

        print("  {:>5s}  {:>7s}  {:s}".format(name, state, assignment))

    info("{} pins in use, {} free: {}".format(
        len(used_pins), len(free_pins), ", ".join(free_pins)))

    passed("GPIO survey complete")
    return True


# ---------------------------------------------------------------------------
# 6. WAV file test
# ---------------------------------------------------------------------------

def test_wav_files():
    divider("WAV File Check")

    sounds_dir = "sounds"
    try:
        files = os.listdir(sounds_dir)
    except OSError:
        info("No sounds/ directory found")
        info("Run install.py to convert and copy WAV files")
        return False

    wav_files = sorted([f for f in files if f.endswith(".wav")])
    print("  Found {} WAV files in sounds/".format(len(wav_files)))

    if not wav_files:
        info("No WAV files in sounds/")
        return False

    # Check a few files
    for fname in wav_files[:5]:
        path = "{}/{}".format(sounds_dir, fname)
        try:
            f = open(path, "rb")
            header = f.read(44)
            f.close()
            if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
                channels = header[22] | (header[23] << 8)
                sample_rate = (header[24] | (header[25] << 8) |
                               (header[26] << 16) | (header[27] << 24))
                bits = header[34] | (header[35] << 8)
                stat = os.stat(path)
                size = stat[6]
                print("  {}: {}ch, {}Hz, {}bit, {:.1f}KB".format(
                    fname, channels, sample_rate, bits, size / 1024))
            else:
                print("  {}: not a valid WAV file".format(fname))
        except Exception as e:
            print("  {}: read error: {}".format(fname, e))

    if len(wav_files) > 5:
        print("  ... and {} more".format(len(wav_files) - 5))

    # Try to play the first WAV file through I2S
    info("Playing first WAV file through I2S...")
    try:
        i2s = machine.I2S(
            0,
            sck=machine.Pin(27),
            ws=machine.Pin(28),
            sd=machine.Pin(26),
            mode=machine.I2S.TX,
            bits=16,
            format=machine.I2S.MONO,
            rate=22050,
            ibuf=8192,
        )

        path = "{}/{}".format(sounds_dir, wav_files[0])
        f = open(path, "rb")
        header = f.read(44)  # skip WAV header
        data_len = (header[40] | (header[41] << 8) |
                    (header[42] << 16) | (header[43] << 24))

        chunk_size = 4096
        buf = bytearray(chunk_size)
        total_read = 0
        max_read = min(data_len, 22050 * 2 * 2)  # max 2 seconds

        passed("Playing: {}".format(wav_files[0]))
        while total_read < max_read:
            n = f.readinto(buf)
            if n is None or n == 0:
                break
            i2s.write(buf[:n])
            total_read += n

        f.close()
        time.sleep(0.2)
        i2s.deinit()
    except Exception as e:
        failed("WAV playback: {}".format(e))
        return False

    passed("WAV file test complete")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n" + "#" * 50)
    print("#  rpiPan Hardware Diagnostic (MicroPython)")
    print("#" * 50)
    print("  Running tests...")

    results = {}

    # 1. Board
    board_type = test_board()
    results["board"] = board_type != "unknown"

    # 2. I2S Audio
    results["i2s"] = test_i2s_audio()
    time.sleep(0.3)

    # 3. ADS1115
    results["ads1115"] = test_ads1115()

    # 4. Mux scan
    results["mux"] = test_mux_scan()

    # 5. GPIO survey
    results["gpio"] = test_gpio_survey()

    # 6. WAV files
    results["wav"] = test_wav_files()

    # Summary
    divider("Summary")
    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print("  {:12s}: {}".format(test_name, status))
    print("\n  {}/{} tests passed".format(passed_count, total))

    if passed_count == total:
        print("\n  All hardware tests passed!")
    else:
        print("\n  Some tests failed. Check wiring and connections.")
        if not results.get("ads1115"):
            print("  - ADS1115: check I2C wiring (SDA=GP4, SCL=GP5, VCC=3.3V)")
        if not results.get("i2s"):
            print("  - I2S: check Pico-Audio HAT is seated correctly")
        if not results.get("wav"):
            print("  - WAV: run 'python install.py' on host")

    # Blink LED to indicate done
    try:
        led = machine.Pin(25, machine.Pin.OUT)
        for _ in range(6):
            led.toggle()
            time.sleep(0.2)
        led.value(0)
    except Exception:
        pass

    print("\nDiagnostic complete. Press Ctrl+C or reset to exit.")
    while True:
        time.sleep(1)


main()
