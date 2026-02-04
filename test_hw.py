"""
test_hw.py - Hardware diagnostic for rpiPan (runs on Pico under CircuitPython)

Copy this file to CIRCUITPY as code.py (or import from REPL) to test:
    1. Board detection
    2. I2S audio output (test tones via Waveshare Pico-Audio)
    3. ADS1115 I2C ADC (voltage readings on all 4 channels)
    4. HW-178 mux scanning (all 29 pads, raw voltages)
    5. GPIO pin state survey

Results are printed to the serial console (screen /dev/tty.usbmodem* 115200).
"""

import time
import board
import digitalio
import math
import array


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pin_exists(name):
    return hasattr(board, name)


def get_pin(name):
    return getattr(board, name, None)


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
# 1. Board detection
# ---------------------------------------------------------------------------

def test_board():
    divider("Board Detection")

    board_id = getattr(board, "board_id", "(unknown)")
    print("  board.board_id = {}".format(board_id))

    # Check for key pins
    pico_pins = ["GP0", "GP4", "GP5", "GP10", "GP14", "GP18", "GP25", "GP26", "GP27", "GP28"]
    present = [p for p in pico_pins if pin_exists(p)]
    print("  Key pins present: {}".format(", ".join(present)))

    # Check LED
    led_pin = get_pin("LED") or get_pin("GP25")
    if led_pin:
        try:
            led = digitalio.DigitalInOut(led_pin)
            led.direction = digitalio.Direction.OUTPUT
            led.value = True
            passed("LED on")
            time.sleep(0.3)
            led.value = False
            led.deinit()
        except Exception as e:
            failed("LED: {}".format(e))
    else:
        info("No LED pin found")

    return board_id


# ---------------------------------------------------------------------------
# 2. I2S audio test
# ---------------------------------------------------------------------------

def test_i2s_audio():
    divider("I2S Audio Output")

    try:
        import audiobusio
    except ImportError:
        failed("audiobusio not available")
        return False

    try:
        import audiocore
    except ImportError:
        failed("audiocore not available")
        return False

    bc_pin = get_pin("GP27")
    ws_pin = get_pin("GP28")
    d_pin = get_pin("GP26")

    if not all([bc_pin, ws_pin, d_pin]):
        failed("I2S pins not found (GP26, GP27, GP28)")
        return False

    info("I2S pins: DATA=GP26, BCK=GP27, LRCK=GP28")

    try:
        audio = audiobusio.I2SOut(bc_pin, ws_pin, d_pin)
        passed("I2SOut initialized")
    except Exception as e:
        failed("I2SOut init: {}".format(e))
        return False

    # Try with audiomixer for polyphony test
    has_mixer = False
    try:
        import audiomixer
        mixer = audiomixer.Mixer(
            voice_count=4,
            sample_rate=22050,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )
        audio.play(mixer)
        has_mixer = True
        passed("audiomixer initialized (4 voices)")
    except ImportError:
        info("audiomixer not available, using direct playback")
    except Exception as e:
        info("audiomixer failed: {}, using direct playback".format(e))

    # Generate test tones
    sample_rate = 22050
    duration_ms = 400
    n_samples = int(sample_rate * duration_ms / 1000)

    # Test frequencies: C4, E4, G4, C5 (major chord)
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
            # Silence test
            buf = array.array("h", [0] * 1000)
            sample = audiocore.RawSample(buf, sample_rate=sample_rate)
            if has_mixer:
                mixer.voice[0].level = 0.0
                mixer.voice[0].play(sample)
            else:
                audio.play(sample)
            time.sleep(0.2)
            info("{}: OK (no sound expected)".format(name))
            continue

        # Generate sine wave
        buf = array.array("h", [0] * n_samples)
        period = sample_rate / freq
        for i in range(n_samples):
            # Apply fade in/out envelope to avoid clicks
            env = 1.0
            fade_samples = int(sample_rate * 0.02)  # 20ms fade
            if i < fade_samples:
                env = i / fade_samples
            elif i > n_samples - fade_samples:
                env = (n_samples - i) / fade_samples
            buf[i] = int(math.sin(2.0 * math.pi * i / period) * 28000 * env)

        sample = audiocore.RawSample(buf, sample_rate=sample_rate)

        try:
            if has_mixer:
                mixer.voice[0].level = 0.7
                mixer.voice[0].play(sample)
            else:
                audio.play(sample)
            passed("{}: playing".format(name))
            time.sleep(duration_ms / 1000.0 + 0.1)
        except Exception as e:
            failed("{}: {}".format(name, e))

    # Polyphony test: play a chord (all at once)
    if has_mixer:
        info("Polyphony test: C major chord...")
        chord_freqs = [262, 330, 392, 523]
        chord_samples = []
        for freq in chord_freqs:
            buf = array.array("h", [0] * n_samples)
            period = sample_rate / freq
            for i in range(n_samples):
                env = 1.0
                fade_samples = int(sample_rate * 0.02)
                if i < fade_samples:
                    env = i / fade_samples
                elif i > n_samples - fade_samples:
                    env = (n_samples - i) / fade_samples
                buf[i] = int(math.sin(2.0 * math.pi * i / period) * 28000 * env)
            chord_samples.append(audiocore.RawSample(buf, sample_rate=sample_rate))

        for i, s in enumerate(chord_samples):
            mixer.voice[i].level = 0.5
            mixer.voice[i].play(s)
            time.sleep(0.03)

        passed("Chord playing (4 voices)")
        time.sleep(0.6)

        for i in range(4):
            mixer.voice[i].stop()

    # Sweep test: rising tone
    info("Frequency sweep: 200-2000 Hz...")
    sweep_duration = 1.5
    sweep_samples = int(sample_rate * sweep_duration)
    # Generate in chunks to save memory
    chunk_size = 2048
    sweep_buf = array.array("h", [0] * chunk_size)
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

        sample = audiocore.RawSample(sweep_buf, sample_rate=sample_rate)
        if has_mixer:
            mixer.voice[0].level = 0.6
            mixer.voice[0].play(sample)
        else:
            audio.play(sample)
        time.sleep(chunk_size / sample_rate)

    passed("Sweep complete")

    # Clean up
    audio.stop()
    audio.deinit()
    passed("I2S audio test complete")
    return True


# ---------------------------------------------------------------------------
# 3. ADS1115 I2C ADC test
# ---------------------------------------------------------------------------

def test_ads1115():
    divider("ADS1115 I2C ADC")

    sda_pin = get_pin("GP4")
    scl_pin = get_pin("GP5")
    if not sda_pin or not scl_pin:
        failed("I2C pins not found (GP4, GP5)")
        return False

    try:
        import busio
    except ImportError:
        failed("busio not available")
        return False

    try:
        i2c = busio.I2C(scl_pin, sda_pin)
        passed("I2C bus initialized (SDA=GP4, SCL=GP5)")
    except Exception as e:
        failed("I2C init: {}".format(e))
        return False

    # Scan I2C bus
    while not i2c.try_lock():
        pass
    try:
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
            i2c.unlock()
            i2c.deinit()
            return False
    finally:
        i2c.unlock()
    i2c.deinit()

    # Try to read channels via adafruit library
    try:
        import adafruit_ads1x15.ads1115 as ADS
        from adafruit_ads1x15.analog_in import AnalogIn
    except ImportError:
        failed("adafruit_ads1x15 library not installed")
        info("Run: python install.py --libs-only /Volumes/CIRCUITPY")
        return False

    try:
        i2c = busio.I2C(scl_pin, sda_pin)
        ads = ADS.ADS1115(i2c)
        ads.data_rate = 860
        passed("ADS1115 driver initialized (860 SPS)")
    except Exception as e:
        failed("ADS1115 driver: {}".format(e))
        return False

    # Read all 4 channels
    channels = [ADS.P0, ADS.P1, ADS.P2, ADS.P3]
    channel_names = ["A0 (Mux A SIG)", "A1 (Mux B SIG)", "A2 (free)", "A3 (free)"]

    print("\n  Channel readings (10 samples averaged):")
    print("  {:20s}  {:>8s}  {:>10s}".format("Channel", "Raw", "Voltage"))
    print("  " + "-" * 42)

    for ch_idx, (ch_pin, ch_name) in enumerate(zip(channels, channel_names)):
        try:
            chan = AnalogIn(ads, ch_pin)
            # Average 10 readings for stability
            raw_sum = 0
            volt_sum = 0.0
            n = 10
            for _ in range(n):
                raw_sum += chan.value
                volt_sum += chan.voltage
                time.sleep(0.002)
            raw_avg = raw_sum // n
            volt_avg = volt_sum / n
            print("  {:20s}  {:>8d}  {:>8.3f} V".format(ch_name, raw_avg, volt_avg))
        except Exception as e:
            print("  {:20s}  ERROR: {}".format(ch_name, e))

    i2c.deinit()
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
        pin = get_pin(name)
        if not pin:
            failed("Select pin {} not found".format(name))
            return False
        dio = digitalio.DigitalInOut(pin)
        dio.direction = digitalio.Direction.OUTPUT
        dio.value = False
        select_pins.append(dio)
    passed("Select pins: {}".format(", ".join(select_names)))

    # Set up enable pins
    en_a_pin = get_pin("GP14")
    en_b_pin = get_pin("GP15")
    en_a = None
    en_b = None
    if en_a_pin:
        en_a = digitalio.DigitalInOut(en_a_pin)
        en_a.direction = digitalio.Direction.OUTPUT
        en_a.value = True  # disabled
    if en_b_pin:
        en_b = digitalio.DigitalInOut(en_b_pin)
        en_b.direction = digitalio.Direction.OUTPUT
        en_b.value = True  # disabled
    passed("Enable pins: GP14 (mux A), GP15 (mux B)")

    # Set up ADS1115
    try:
        import busio
        import adafruit_ads1x15.ads1115 as ADS
        from adafruit_ads1x15.analog_in import AnalogIn
    except ImportError:
        failed("adafruit_ads1x15 not available, cannot read mux")
        for p in select_pins:
            p.deinit()
        if en_a:
            en_a.deinit()
        if en_b:
            en_b.deinit()
        return False

    sda_pin = get_pin("GP4")
    scl_pin = get_pin("GP5")
    try:
        i2c = busio.I2C(scl_pin, sda_pin)
        ads = ADS.ADS1115(i2c)
        ads.data_rate = 860
        adc_a = AnalogIn(ads, ADS.P0)
        adc_b = AnalogIn(ads, ADS.P1)
    except Exception as e:
        failed("ADS1115 init for mux scan: {}".format(e))
        for p in select_pins:
            p.deinit()
        if en_a:
            en_a.deinit()
        if en_b:
            en_b.deinit()
        return False

    def set_channel(channel):
        for i in range(4):
            select_pins[i].value = bool(channel & (1 << i))

    def enable_mux(mux_id):
        if en_a:
            en_a.value = (mux_id != "a")
        if en_b:
            en_b.value = (mux_id != "b")

    def read_mux(mux_id, channel):
        enable_mux(mux_id)
        set_channel(channel)
        time.sleep(0.001)  # settle
        if mux_id == "a":
            return adc_a.value, adc_a.voltage
        else:
            return adc_b.value, adc_b.voltage

    # Pad assignment (from pan_layout.json)
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
    if en_a:
        en_a.value = True
    if en_b:
        en_b.value = True

    print("\n  Active pads (above threshold {}): {}".format(threshold, active_count))
    if active_count == 0:
        info("No pads active (expected if nothing is being pressed)")
    elif active_count > 5:
        info("Many pads active — check for noise or floating inputs")

    # Also scan unused channels on mux B (C13-C15)
    print("\n  Unused mux B channels:")
    for ch in [13, 14, 15]:
        raw, voltage = read_mux("b", ch)
        print("    B/C{}: raw={}, voltage={:.3f}V".format(ch, raw, voltage))

    # Clean up
    for p in select_pins:
        p.deinit()
    if en_a:
        en_a.deinit()
    if en_b:
        en_b.deinit()
    i2c.deinit()

    passed("Mux scan complete")
    return True


# ---------------------------------------------------------------------------
# 5. GPIO pin survey
# ---------------------------------------------------------------------------

def test_gpio_survey():
    divider("GPIO Pin Survey")

    # All GP pins on the Pico
    all_pins = []
    for i in range(29):
        name = "GP{}".format(i)
        if pin_exists(name):
            all_pins.append(name)

    # Pins we know are in use
    used_pins = {
        "GP4": "I2C SDA (ADS1115)",
        "GP5": "I2C SCL (ADS1115)",
        "GP10": "Mux S0",
        "GP11": "Mux S1",
        "GP12": "Mux S2",
        "GP13": "Mux S3",
        "GP14": "Mux A EN",
        "GP15": "Mux B EN",
        "GP25": "LED",
        "GP26": "I2S DATA (Pico-Audio)",
        "GP27": "I2S BCK (Pico-Audio)",
        "GP28": "I2S LRCK (Pico-Audio)",
    }

    print("\n  {:>5s}  {:>7s}  {:s}".format("Pin", "State", "Assignment"))
    print("  " + "-" * 45)

    for name in all_pins:
        assignment = used_pins.get(name, "(free)")
        pin = get_pin(name)
        state = "?"

        # Skip pins currently in use by I2S/I2C (reading them would conflict)
        if name in ("GP26", "GP27", "GP28", "GP4", "GP5"):
            state = "in use"
        elif name in used_pins:
            state = "config"
        else:
            # Try to read the pin state
            try:
                dio = digitalio.DigitalInOut(pin)
                dio.direction = digitalio.Direction.INPUT
                dio.pull = digitalio.Pull.UP
                time.sleep(0.001)
                val = dio.value
                state = "HIGH" if val else "LOW "
                dio.deinit()
            except Exception:
                state = "error"

        print("  {:>5s}  {:>7s}  {:s}".format(name, state, assignment))

    # Count free pins
    free = [p for p in all_pins if p not in used_pins]
    info("{} pins in use, {} free: {}".format(
        len(used_pins), len(free), ", ".join(free)))

    passed("GPIO survey complete")
    return True


# ---------------------------------------------------------------------------
# 6. WAV file test
# ---------------------------------------------------------------------------

def test_wav_files():
    divider("WAV File Check")

    import os

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
                # Parse WAV header
                channels = header[22] | (header[23] << 8)
                sample_rate = (header[24] | (header[25] << 8) |
                               (header[26] << 16) | (header[27] << 24))
                bits = header[34] | (header[35] << 8)
                size = os.stat(path)[6]
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
        import audiobusio
        import audiocore
        import audiomixer

        audio = audiobusio.I2SOut(
            get_pin("GP27"), get_pin("GP28"), get_pin("GP26"))
        mixer = audiomixer.Mixer(
            voice_count=1,
            sample_rate=22050,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )
        audio.play(mixer)

        path = "{}/{}".format(sounds_dir, wav_files[0])
        f = open(path, "rb")
        wav = audiocore.WaveFile(f)
        mixer.voice[0].level = 0.8
        mixer.voice[0].play(wav)
        passed("Playing: {}".format(wav_files[0]))
        time.sleep(1.5)
        mixer.voice[0].stop()
        f.close()
        audio.stop()
        audio.deinit()
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
    print("#  rpiPan Hardware Diagnostic")
    print("#" * 50)
    print("  Time: running tests...")

    results = {}

    # 1. Board
    board_id = test_board()
    results["board"] = board_id != "(unknown)"

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
            print("  - WAV: run 'python install.py --libs' on host")

    # Blink LED to indicate done
    led_pin = get_pin("LED") or get_pin("GP25")
    if led_pin:
        try:
            led = digitalio.DigitalInOut(led_pin)
            led.direction = digitalio.Direction.OUTPUT
            for _ in range(6):
                led.value = not led.value
                time.sleep(0.2)
            led.value = False
            led.deinit()
        except Exception:
            pass

    print("\nDiagnostic complete. Press Ctrl+C or reset to exit.")
    while True:
        time.sleep(1)


main()
