#!/usr/bin/env python3
"""
install.py - Prepare, convert, and install rpiPan to a Pico.

Downloads WAV samples from urbanPan (or pitch-shifts from lower octaves),
converts to 16-bit mono 22050 Hz, then deploys to the Pico. Supports both
MicroPython (default) and CircuitPython platforms.

Sound preparation follows panipuri's cascading fallback approach:
  1. Already exists in source directory
  2. Download from urbanPan GitHub repo (layer 2, forte)
  3. Pitch-shift from an octave-below sample
No external dependencies — uses only Python stdlib.

Usage:
    python install.py                          # Download + convert + deploy (MicroPython)
    python install.py --platform circuitpython /Volumes/CIRCUITPY  # CircuitPython
    python install.py --source ../panipuri/sounds  # Use existing sounds directory
    python install.py --prepare-only           # Just download/prepare source sounds
    python install.py --dry-run                # Show what would be done
    python install.py --convert-only           # Just convert, don't deploy
    python install.py --no-download            # Skip downloading, use existing only
    python install.py --platform circuitpython --libs  # Also install CP libraries
    python install.py --platform circuitpython --libs-only /Volumes/CIRCUITPY
"""

import os
import sys
import json
import wave
import struct
import shutil
import argparse
import zipfile
import tempfile

try:
    from urllib.request import urlopen, Request
    from urllib.error import URLError
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Default paths
if sys.platform == "darwin":
    DEFAULT_DRIVE = "/Volumes/CIRCUITPY"
elif sys.platform == "win32":
    DEFAULT_DRIVE = "D:\\"
else:
    DEFAULT_DRIVE = "/media/{}/CIRCUITPY".format(os.environ.get("USER", "pi"))

DEFAULT_SOURCE = os.path.join(SCRIPT_DIR, "sounds_source")

# Target sample rate for Pico (22050 Hz mono is a good balance of
# quality vs. CPU/RAM on the RP2040)
TARGET_RATE = 22050
TARGET_CHANNELS = 1
TARGET_SAMPWIDTH = 2  # 16-bit

# Default size budget for WAV sounds in MicroPython staging
MP_SOUNDS_MAX_BYTES = 1024 * 1024  # 1 MB


# ---------------------------------------------------------------------------
# WAV conversion
# ---------------------------------------------------------------------------

def convert_wav(src_path, dst_path, target_rate=TARGET_RATE):
    """Convert a WAV file to 16-bit mono at the target sample rate.

    Uses only the Python standard library (wave + struct) plus basic
    linear interpolation for resampling. No numpy/scipy required.
    """
    with wave.open(src_path, "rb") as src:
        src_rate = src.getframerate()
        src_channels = src.getnchannels()
        src_nframes = src.getnframes()
        src_width = src.getsampwidth()

        # Read all frames as bytes
        raw = src.readframes(src_nframes)

    # Decode samples to list of integers
    if src_width == 1:
        # 8-bit unsigned
        samples = [b - 128 for b in raw]
        scale = 256  # scale up to 16-bit range
    elif src_width == 2:
        # 16-bit signed little-endian
        samples = list(struct.unpack("<{}h".format(len(raw) // 2), raw))
        scale = 1
    elif src_width == 3:
        # 24-bit signed - take top 16 bits
        samples = []
        for i in range(0, len(raw), 3):
            val = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if val >= 0x800000:
                val -= 0x1000000
            samples.append(val >> 8)
        scale = 1
    else:
        raise ValueError("Unsupported sample width: {} bytes".format(src_width))

    # Mix down to mono if stereo/multi-channel
    if src_channels > 1:
        mono = []
        for i in range(0, len(samples), src_channels):
            chunk = samples[i:i + src_channels]
            mono.append(sum(chunk) // len(chunk))
        samples = mono

    # Scale to 16-bit if needed
    if scale != 1:
        samples = [s * scale for s in samples]

    # Resample if rates differ
    if src_rate != target_rate:
        samples = resample(samples, src_rate, target_rate)

    # Clamp to 16-bit range
    samples = [max(-32768, min(32767, int(s))) for s in samples]

    # Write output
    with wave.open(dst_path, "wb") as dst:
        dst.setnchannels(TARGET_CHANNELS)
        dst.setsampwidth(TARGET_SAMPWIDTH)
        dst.setframerate(target_rate)
        dst.writeframes(struct.pack("<{}h".format(len(samples)), *samples))

    return len(samples)


def resample(samples, src_rate, dst_rate):
    """Resample audio using linear interpolation.

    Good enough for integer-ratio conversions like 44100 -> 22050.
    For 2:1 downsampling, applies a simple averaging filter first.
    """
    ratio = src_rate / dst_rate
    src_len = len(samples)
    dst_len = int(src_len / ratio)

    # For exact 2:1 downsampling, average adjacent samples (anti-alias)
    if src_rate == 2 * dst_rate:
        result = []
        for i in range(0, src_len - 1, 2):
            result.append((samples[i] + samples[i + 1]) // 2)
        return result

    # General case: linear interpolation
    result = []
    for i in range(dst_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx

        if idx + 1 < src_len:
            val = samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
        else:
            val = samples[idx] if idx < src_len else 0
        result.append(int(val))

    return result


def trim_wav(src_path, dst_path, max_samples, fade_samples=1102):
    """Copy a WAV file, trimming to max_samples with a fade-out.

    Expects 16-bit mono input (as produced by convert_wav).
    fade_samples defaults to ~50ms at 22050 Hz.
    If the file is already short enough, copies it unchanged.
    Returns the number of samples in the output file.
    """
    with wave.open(src_path, "rb") as src:
        params = src.getparams()
        n_frames = src.getnframes()
        raw = src.readframes(n_frames)

    n_samples = len(raw) // 2
    if n_samples <= max_samples:
        shutil.copy(src_path, dst_path)
        return n_samples

    # Decode, truncate
    samples = list(struct.unpack("<{}h".format(n_samples), raw))
    samples = samples[:max_samples]

    # Apply linear fade-out over last fade_samples
    fade_len = min(fade_samples, len(samples))
    for i in range(fade_len):
        pos = len(samples) - fade_len + i
        factor = 1.0 - (i / fade_len)
        samples[pos] = int(samples[pos] * factor)

    with wave.open(dst_path, "wb") as dst:
        dst.setnchannels(params.nchannels)
        dst.setsampwidth(params.sampwidth)
        dst.setframerate(params.framerate)
        dst.writeframes(struct.pack("<{}h".format(len(samples)), *samples))

    return len(samples)


# ---------------------------------------------------------------------------
# Sound preparation (download from urbanPan / pitch-shift)
# ---------------------------------------------------------------------------

# urbanPan GitHub raw URL for forte (layer 2) samples
URBANPAN_BASE_URL = (
    "https://raw.githubusercontent.com/urbansmash/urbanPan/master/urbanPan/Samples"
)

# Note name -> urbanPan filename component (sharps use uppercase S)
NAME_TO_URBANPAN = {
    "C": "C", "C#": "CS", "Db": "CS",
    "D": "D", "D#": "DS", "Eb": "DS",
    "E": "E",
    "F": "F", "F#": "FS", "Gb": "FS",
    "G": "G", "G#": "GS", "Ab": "GS",
    "A": "A", "A#": "AS", "Bb": "AS",
    "B": "B",
}

# Note name -> filename-safe name (sharps use lowercase s)
NAME_TO_FILESAFE = {
    "C": "C", "C#": "Cs", "Db": "Cs",
    "D": "D", "D#": "Ds", "Eb": "Ds",
    "E": "E",
    "F": "F", "F#": "Fs", "Gb": "Fs",
    "G": "G", "G#": "Gs", "Ab": "Gs",
    "A": "A", "A#": "As", "Bb": "As",
    "B": "B",
}


def sound_filename(name, octave):
    """Get the output filename for a note (e.g. 'Fs4.wav')."""
    safe = NAME_TO_FILESAFE.get(name, name.replace("#", "s"))
    return "{}{}.wav".format(safe, octave)


def urbanpan_filename(name, octave):
    """Get the urbanPan sample filename (e.g. '2-FS4.wav')."""
    up = NAME_TO_URBANPAN.get(name)
    if up is None:
        return None
    return "2-{}{}.wav".format(up, octave)


def download_urbanpan(name, octave, dest_path):
    """Download a forte sample from urbanPan GitHub. Returns True on success."""
    if not HAS_URLLIB:
        return False
    fname = urbanpan_filename(name, octave)
    if fname is None:
        return False
    url = "{}/{}".format(URBANPAN_BASE_URL, fname)
    try:
        req = Request(url, headers={"User-Agent": "rpiPan-installer"})
        resp = urlopen(req, timeout=30)
        with open(dest_path, "wb") as f:
            f.write(resp.read())
        return True
    except Exception:
        return False


def pitch_shift_octave_up(src_path, dest_path):
    """Shift a WAV file up one octave by resampling to half length.

    Reads the source WAV, averages adjacent sample pairs (anti-alias),
    and writes at the same sample rate with half the samples.
    Stdlib only (wave + struct). Handles mono and stereo input.
    Returns True on success.
    """
    try:
        with wave.open(src_path, "rb") as src:
            src_rate = src.getframerate()
            channels = src.getnchannels()
            width = src.getsampwidth()
            n_frames = src.getnframes()
            raw = src.readframes(n_frames)
    except Exception:
        return False

    # Decode to 16-bit samples
    if width == 2:
        n_samples = len(raw) // 2
        samples = list(struct.unpack("<{}h".format(n_samples), raw))
    elif width == 1:
        samples = [(b - 128) * 256 for b in raw]
    elif width == 3:
        samples = []
        for i in range(0, len(raw), 3):
            val = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if val >= 0x800000:
                val -= 0x1000000
            samples.append(val >> 8)
    else:
        return False

    # Pitch-shift: average adjacent frame pairs (anti-alias + downsample)
    samples_per_frame = channels
    n_frame_pairs = len(samples) // (samples_per_frame * 2)

    shifted = []
    for i in range(n_frame_pairs):
        base = i * samples_per_frame * 2
        for ch in range(channels):
            s1 = samples[base + ch]
            s2 = samples[base + samples_per_frame + ch]
            shifted.append((s1 + s2) // 2)

    # Normalize to 82% peak to prevent clipping (matches panipuri)
    if shifted:
        peak = max(abs(s) for s in shifted)
        target_peak = int(32767 * 0.82)
        if peak > target_peak:
            scale = target_peak / peak
            shifted = [int(s * scale) for s in shifted]

    # Write output at same sample rate
    with wave.open(dest_path, "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(2)
        dst.setframerate(src_rate)
        dst.writeframes(struct.pack("<{}h".format(len(shifted)), *shifted))

    return True


def prepare_source_sounds(layout_path, source_dir, force=False, dry_run=False,
                          no_download=False):
    """Download or generate source WAV files for all notes in the layout.

    Cascading fallback (same approach as panipuri's prepare_sounds.py):
      1. Already exists in source_dir
      2. Download from urbanPan GitHub repo (layer 2, forte)
      3. Pitch-shift from an octave-below sample

    Uses only Python stdlib — no numpy or scipy needed.
    Returns (available_filenames, stats_dict).
    """
    if not os.path.isfile(layout_path):
        print("ERROR: pan_layout.json not found")
        return [], {}

    # Read layout to get needed notes
    with open(layout_path, "r") as f:
        data = json.load(f)

    notes = data.get("notes", [])
    if not notes:
        print("ERROR: No notes found in layout")
        return [], {}

    if not dry_run:
        os.makedirs(source_dir, exist_ok=True)

    print("--- Preparing source sounds ---")
    print("Source directory: {}".format(source_dir))
    if no_download:
        print("(Download disabled — using existing files only)")
    print()

    stats = {"exists": 0, "downloaded": 0, "shifted": 0, "failed": 0}
    available = []
    sym = {"exists": ".", "downloaded": "D", "shifted": "S", "failed": "!"}

    for note in notes:
        name = note["name"]
        octave = note["octave"]
        fname = sound_filename(name, octave)
        dest = os.path.join(source_dir, fname)

        # 1. Already exists
        if os.path.isfile(dest) and not force:
            size = os.path.getsize(dest) // 1024
            print("  . {:3s}{}  {:10s}  exists ({} KB)".format(
                name, octave, fname, size))
            stats["exists"] += 1
            available.append(fname)
            continue

        if no_download:
            print("  ! {:3s}{}  {:10s}  missing (download disabled)".format(
                name, octave, fname))
            stats["failed"] += 1
            continue

        if dry_run:
            print("  D {:3s}{}  {:10s}  would download".format(
                name, octave, fname))
            stats["downloaded"] += 1
            available.append(fname)
            continue

        # 2. Download from urbanPan
        if download_urbanpan(name, octave, dest):
            size = os.path.getsize(dest) // 1024
            print("  D {:3s}{}  {:10s}  downloaded ({} KB)".format(
                name, octave, fname, size))
            stats["downloaded"] += 1
            available.append(fname)
            continue

        # 3. Pitch-shift from lower octave
        lower_octave = octave - 1
        lower_fname = sound_filename(name, lower_octave)
        lower_path = os.path.join(source_dir, lower_fname)

        # Try existing lower-octave file in source dir
        shifted = False
        if os.path.isfile(lower_path):
            if pitch_shift_octave_up(lower_path, dest):
                shifted = True

        # Try downloading the lower octave, then shift
        if not shifted:
            tmp_path = os.path.join(source_dir, "_tmp_lower.wav")
            if download_urbanpan(name, lower_octave, tmp_path):
                if pitch_shift_octave_up(tmp_path, dest):
                    shifted = True
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        if shifted:
            size = os.path.getsize(dest) // 1024
            print("  S {:3s}{}  {:10s}  shifted from {}{}  ({} KB)".format(
                name, octave, fname, name, lower_octave, size))
            stats["shifted"] += 1
            available.append(fname)
            continue

        print("  ! {:3s}{}  {:10s}  FAILED".format(name, octave, fname))
        stats["failed"] += 1

    # Summary
    print()
    parts = []
    if stats["exists"]:
        parts.append("{} already existed".format(stats["exists"]))
    if stats["downloaded"]:
        parts.append("{} downloaded".format(stats["downloaded"]))
    if stats["shifted"]:
        parts.append("{} pitch-shifted".format(stats["shifted"]))
    if stats["failed"]:
        parts.append("{} FAILED".format(stats["failed"]))
    print("Prepared: {} notes ({})".format(len(available), ", ".join(parts)))

    return available, stats


# ---------------------------------------------------------------------------
# Layout reading
# ---------------------------------------------------------------------------

def get_needed_files(layout_path):
    """Read pan_layout.json and return list of WAV filenames needed."""
    NOTE_NAMES_FILE = [
        "C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"
    ]
    NOTE_NAMES_MAP = {
        "C": 0, "C#": 1, "Db": 1,
        "D": 2, "D#": 3, "Eb": 3,
        "E": 4, "Fb": 4, "E#": 5,
        "F": 5, "F#": 6, "Gb": 6,
        "G": 7, "G#": 8, "Ab": 8,
        "A": 9, "A#": 10, "Bb": 10,
        "B": 11, "Cb": 11, "B#": 0,
    }

    with open(layout_path, "r") as f:
        data = json.load(f)

    filenames = []
    for entry in data.get("notes", []):
        name = entry["name"]
        octave = entry["octave"]
        semitone = NOTE_NAMES_MAP.get(name)
        if semitone is None:
            continue
        midi = (octave + 1) * 12 + semitone
        note_idx = midi % 12
        oct = (midi // 12) - 1
        fname = "{}{}.wav".format(NOTE_NAMES_FILE[note_idx], oct)
        filenames.append(fname)

    return sorted(set(filenames))


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def convert_samples(source_dir, converted_dir, layout_path, target_rate,
                    dry_run=False, force=False, no_download=False):
    """Convert WAV samples from source to converted directory.

    If the source directory is missing or incomplete, automatically
    downloads sounds from urbanPan first.

    Returns (available_files, success) where available_files is a list
    of filenames that were converted (or already up to date).
    """
    source_dir = os.path.abspath(source_dir)

    # Auto-prepare source sounds if directory is missing or incomplete
    needs_prep = not os.path.isdir(source_dir)
    if not needs_prep and os.path.isfile(layout_path):
        needed = get_needed_files(layout_path)
        existing = [f for f in needed
                    if os.path.isfile(os.path.join(source_dir, f))]
        if len(existing) < len(needed):
            needs_prep = True

    prepared_files = None
    if needs_prep and not no_download:
        print()
        prepared_files, prep_stats = prepare_source_sounds(
            layout_path, source_dir, force=force, dry_run=dry_run)
        if not prepared_files:
            print("ERROR: Could not prepare source sounds")
            print("  Check your internet connection, or use --source to")
            print("  point to an existing sounds directory.")
            return [], False
        print()

    # Validate source
    if not os.path.isdir(source_dir):
        if dry_run and prepared_files:
            # In dry-run mode, use the prepared file list directly
            pass
        else:
            print("ERROR: Source sounds directory not found: {}".format(source_dir))
            print("  Run without --no-download to auto-download from urbanPan,")
            print("  or specify with --source, e.g.:")
            print("    python install.py --source /path/to/panipuri/sounds")
            return [], False

    if not os.path.isfile(layout_path):
        print("ERROR: pan_layout.json not found in {}".format(
            os.path.dirname(layout_path)))
        return [], False

    needed = get_needed_files(layout_path)
    print("Notes in layout: {} WAV files needed".format(len(needed)))

    # In dry-run with preparation, use the prepared list instead of filesystem
    if dry_run and prepared_files and not os.path.isdir(source_dir):
        available = [f for f in needed if f in prepared_files]
        missing = [f for f in needed if f not in prepared_files]
    else:
        available = []
        missing = []
        for fname in needed:
            src = os.path.join(source_dir, fname)
            if os.path.isfile(src):
                available.append(fname)
            else:
                missing.append(fname)

    if missing:
        print("WARNING: {} source files missing:".format(len(missing)))
        for f in missing:
            print("    {}".format(f))
    print("Found {}/{} source WAV files\n".format(len(available), len(needed)))

    if not available:
        print("ERROR: No source WAV files found in {}".format(source_dir))
        return [], False

    print("--- Converting samples ---")
    if not dry_run:
        os.makedirs(converted_dir, exist_ok=True)

    converted = 0
    skipped = 0
    errors = 0

    for fname in available:
        src = os.path.join(source_dir, fname)
        dst = os.path.join(converted_dir, fname)

        # In dry-run with prepared files, source may not exist on disk yet
        src_exists = os.path.isfile(src)

        if src_exists and os.path.isfile(dst) and not force:
            src_mtime = os.path.getmtime(src)
            dst_mtime = os.path.getmtime(dst)
            if dst_mtime >= src_mtime:
                skipped += 1
                continue

        src_size = os.path.getsize(src) / 1024 if src_exists else 0

        if dry_run:
            if src_exists:
                print("  Would convert: {} ({:.0f} KB)".format(fname, src_size))
            else:
                print("  Would convert: {}".format(fname))
            converted += 1
            continue

        try:
            n_samples = convert_wav(src, dst, target_rate)
            dst_size = os.path.getsize(dst) / 1024
            print("  {} ({:.0f}K -> {:.0f}K, {} samples)".format(
                fname, src_size, dst_size, n_samples))
            converted += 1
        except Exception as e:
            print("  ERROR converting {}: {}".format(fname, e))
            errors += 1

    print("\nConverted: {}, Skipped (up to date): {}, Errors: {}".format(
        converted, skipped, errors))

    return available, True


def stage_micropython(converted_dir, available, layout_path, dry_run=False,
                      max_sounds_bytes=MP_SOUNDS_MAX_BYTES):
    """Stage MicroPython files for upload via Thonny or mpremote.

    Creates micropython_staging/ with main.py, test_hw.py,
    pan_layout.json, and sounds/.  Trims WAV samples with a fade-out
    if the total sounds size would exceed max_sounds_bytes.
    """
    staging = os.path.join(SCRIPT_DIR, "micropython_staging")
    main_src = os.path.join(SCRIPT_DIR, "main_mp.py")
    test_src = os.path.join(SCRIPT_DIR, "test_hw_mp.py")
    diskinfo_src = os.path.join(SCRIPT_DIR, "diskinfo_mp.py")

    print("\n--- Staging MicroPython files ---")

    if not dry_run:
        os.makedirs(staging, exist_ok=True)

    # 1. Copy diskinfo_mp.py -> diskinfo.py
    code_size = 0
    dst = os.path.join(staging, "diskinfo.py")
    if os.path.isfile(diskinfo_src):
        if dry_run:
            print("  Would copy: diskinfo_mp.py -> diskinfo.py")
            code_size += os.path.getsize(diskinfo_src)
        else:
            shutil.copy(diskinfo_src, dst)
            sz = os.path.getsize(dst)
            code_size += sz
            print("  diskinfo.py ({:.0f} KB)".format(sz / 1024))

    # 3. Copy main_mp.py -> main.py
    dst = os.path.join(staging, "main.py")
    if dry_run:
        print("  Would copy: main_mp.py -> main.py")
        code_size += os.path.getsize(main_src)
    else:
        shutil.copy(main_src, dst)
        sz = os.path.getsize(dst)
        code_size += sz
        print("  main.py ({:.0f} KB)".format(sz / 1024))

    # 4. Copy test_hw_mp.py -> test_hw.py
    dst = os.path.join(staging, "test_hw.py")
    if os.path.isfile(test_src):
        if dry_run:
            print("  Would copy: test_hw_mp.py -> test_hw.py")
            code_size += os.path.getsize(test_src)
        else:
            shutil.copy(test_src, dst)
            sz = os.path.getsize(dst)
            code_size += sz
            print("  test_hw.py ({:.0f} KB)".format(sz / 1024))

    # 5. Copy pan_layout.json
    dst = os.path.join(staging, "pan_layout.json")
    if dry_run:
        print("  Would copy: pan_layout.json")
        code_size += os.path.getsize(layout_path)
    else:
        shutil.copy(layout_path, dst)
        sz = os.path.getsize(dst)
        code_size += sz
        print("  pan_layout.json ({:.0f} KB)".format(sz / 1024))

    # 6. Copy converted sounds, trimming if needed to fit budget
    sounds_dst = os.path.join(staging, "sounds")
    if not dry_run:
        os.makedirs(sounds_dst, exist_ok=True)

    n_files = len([f for f in available
                   if os.path.isfile(os.path.join(converted_dir, f))])

    # Check if trimming is needed
    current_sound_size = sum(
        os.path.getsize(os.path.join(converted_dir, f))
        for f in available
        if os.path.isfile(os.path.join(converted_dir, f)))

    max_samples = None
    if current_sound_size > max_sounds_bytes and n_files > 0:
        # Calculate max samples per file to fit budget
        # Each file = max_samples * 2 (bytes) + 44 (header)
        bytes_per_file = max_sounds_bytes // n_files
        max_samples = (bytes_per_file - 44) // 2
        if max_samples < 2205:  # minimum 0.1s
            max_samples = 2205
        duration = max_samples / TARGET_RATE
        print("  Trimming samples to {:.1f}s (sounds budget {:.1f} MB)".format(
            duration, max_sounds_bytes / 1024 / 1024))

    copied = 0
    total_size = 0
    for fname in available:
        src = os.path.join(converted_dir, fname)
        dst_file = os.path.join(sounds_dst, fname)
        if not os.path.isfile(src):
            continue
        if dry_run:
            if max_samples:
                print("  Would trim: sounds/{}".format(fname))
            else:
                print("  Would copy: sounds/{}".format(fname))
        else:
            if max_samples:
                trim_wav(src, dst_file, max_samples)
            else:
                shutil.copy(src, dst_file)
            sz = os.path.getsize(dst_file)
            total_size += sz
        copied += 1

    print("  sounds/ ({} files, {:.0f} KB total)".format(
        copied, total_size / 1024))

    # Report sizes
    print("  Total sounds: {:.1f} KB ({:.2f} MB)".format(
        total_size / 1024, total_size / 1024 / 1024))
    print("  Total staging: {:.1f} KB ({:.2f} MB)".format(
        (code_size + total_size) / 1024, (code_size + total_size) / 1024 / 1024))

    # Check max_voices
    try:
        with open(layout_path, "r") as f:
            data = json.load(f)
        max_v = data.get("hardware", {}).get("max_voices", 6)
        if max_v > 6:
            print("\nNOTE: pan_layout.json has \"max_voices\": {}. MicroPython".format(
                max_v))
            print("  software mixing works best with 6 or fewer voices on RP2040.")
    except Exception:
        pass

    # Try uploading via mpremote
    print("\n" + "=" * 50)
    if dry_run:
        print("DRY RUN complete. No files were modified.")
        print("\nTo upload to your Pico, run without --dry-run.")
        return True

    print("MicroPython files staged in: {}".format(staging))

    uploaded = _upload_mpremote(staging)
    if uploaded:
        print("\nUpload complete. Reset the Pico to run.")
    else:
        print("\nTo upload manually:")
        print()
        print("  Option 1 — Thonny IDE:")
        print("    1. Open Thonny, connect to Pico")
        print("    2. View > Files to open the file browser")
        print("    3. Navigate to {}".format(staging))
        print("    4. Right-click each file/folder and 'Upload to /'")
        print()
        print("  Option 2 — mpremote (command line):")
        print("    pip install mpremote")
        print("    cd {}".format(staging))
        print("    mpremote fs cp diskinfo.py :diskinfo.py")
        print("    mpremote fs cp main.py :main.py")
        print("    mpremote fs cp pan_layout.json :pan_layout.json")
        print("    mpremote fs cp test_hw.py :test_hw.py")
        print("    mpremote fs cp -r sounds/ :")
        print()
        print("Then reset the Pico to run.")

    return True


def _upload_mpremote(staging):
    """Try to upload staged files to Pico via mpremote.

    Installs mpremote via pip if not found. Returns True on success.
    """
    import subprocess

    # Check if mpremote is available, install if not
    try:
        subprocess.run(["mpremote", "version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("mpremote not found, installing...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "mpremote"],
                capture_output=True, check=True)
            print("  Installed mpremote.")
        except subprocess.CalledProcessError as e:
            print("  Could not install mpremote: {}".format(e))
            return False

    # Clean old files on Pico (preserve .txt files like boot_out.txt)
    print("\nCleaning old files on Pico...")
    cleanup_code = (
        "import os\n"
        "def rmtree(p):\n"
        "    for f in os.listdir(p):\n"
        "        fp = p.rstrip('/') + '/' + f\n"
        "        try:\n"
        "            os.remove(fp)\n"
        "        except:\n"
        "            rmtree(fp)\n"
        "            os.rmdir(fp)\n"
        "removed = []\n"
        "for f in os.listdir('/'):\n"
        "    if f.endswith('.txt'):\n"
        "        continue\n"
        "    fp = '/' + f\n"
        "    try:\n"
        "        os.remove(fp)\n"
        "        removed.append(f)\n"
        "    except:\n"
        "        try:\n"
        "            rmtree(fp)\n"
        "            os.rmdir(fp)\n"
        "            removed.append(f + '/')\n"
        "        except Exception as e:\n"
        "            print('  skip:', f, e)\n"
        "print('Removed:', ', '.join(removed) if removed else '(none)')\n"
    )
    try:
        result = subprocess.run(
            ["mpremote", "exec", cleanup_code],
            capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        if output:
            print("  {}".format(output))
    except subprocess.CalledProcessError as e:
        print("  WARNING: cleanup failed: {}".format(e))
    except subprocess.TimeoutExpired:
        print("  WARNING: cleanup timed out")

    # Upload files
    print("\nUploading to Pico via mpremote...")
    files = [
        ("diskinfo.py", ":diskinfo.py"),
        ("main.py", ":main.py"),
        ("pan_layout.json", ":pan_layout.json"),
        ("test_hw.py", ":test_hw.py"),
    ]
    for local, remote in files:
        src = os.path.join(staging, local)
        if not os.path.isfile(src):
            continue
        print("  {} -> {}".format(local, remote))
        try:
            subprocess.run(
                ["mpremote", "fs", "cp", src, remote],
                check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print("  ERROR uploading {}: {}".format(local, e))
            print("  Is the Pico connected and not in use by another program?")
            return False

    # Upload sounds directory recursively
    sounds_dir = os.path.join(staging, "sounds")
    if os.path.isdir(sounds_dir):
        print("  sounds/ -> :sounds/")
        try:
            subprocess.run(
                ["mpremote", "fs", "cp", "-r", sounds_dir, ":"],
                check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print("  ERROR uploading sounds/: {}".format(e))
            return False

    return True


def install_circuitpython(drive_path, converted_dir, available, layout_path,
                          dry_run=False):
    """Copy CircuitPython files to CIRCUITPY drive."""
    code_path = os.path.join(SCRIPT_DIR, "code.py")

    if not os.path.isdir(drive_path):
        print("\nERROR: Drive not found: {}".format(drive_path))
        print("  Is the Pico connected and mounted?")
        print("  Specify drive path: python install.py --platform circuitpython /path/to/CIRCUITPY")
        return False

    print("\n--- Installing to {} ---".format(drive_path))

    # 1. Copy code.py
    dst = os.path.join(drive_path, "code.py")
    if dry_run:
        print("  Would copy: code.py")
    else:
        shutil.copy(code_path, dst)
        print("  code.py ({:.0f} KB)".format(os.path.getsize(dst) / 1024))

    # 2. Copy pan_layout.json
    dst = os.path.join(drive_path, "pan_layout.json")
    if dry_run:
        print("  Would copy: pan_layout.json")
    else:
        shutil.copy(layout_path, dst)
        print("  pan_layout.json ({:.0f} KB)".format(os.path.getsize(dst) / 1024))

    # 3. Copy converted sounds/
    sounds_dst = os.path.join(drive_path, "sounds")
    if not dry_run:
        os.makedirs(sounds_dst, exist_ok=True)

    copied = 0
    total_size = 0
    for fname in available:
        src = os.path.join(converted_dir, fname)
        dst = os.path.join(sounds_dst, fname)
        if not os.path.isfile(src):
            continue
        if dry_run:
            print("  Would copy: sounds/{}".format(fname))
        else:
            shutil.copy(src, dst)
            sz = os.path.getsize(dst)
            total_size += sz
        copied += 1

    print("  sounds/ ({} files, {:.0f} KB total)".format(
        copied, total_size / 1024))

    # Summary
    drive_used = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, dirs, files in os.walk(drive_path)
        for f in files
    ) if not dry_run else 0

    print("\n" + "=" * 50)
    if dry_run:
        print("DRY RUN complete. No files were modified.")
    else:
        print("Install complete!")
        print("  Drive usage: {:.0f} KB".format(drive_used / 1024))
    print("  Files on Pico:")
    print("    code.py")
    print("    pan_layout.json")
    print("    sounds/ ({} WAV files)".format(copied))
    print("\nThe Pico should restart automatically and play the demo.")

    return True


def install(drive_path, source_dir, platform="micropython", dry_run=False,
            convert_only=False, target_rate=TARGET_RATE, force=False,
            max_sounds_bytes=MP_SOUNDS_MAX_BYTES, no_download=False):
    """Convert samples and install to Pico."""

    layout_path = os.path.join(SCRIPT_DIR, "pan_layout.json")
    converted_dir = os.path.join(SCRIPT_DIR, "sounds_converted")
    source_dir = os.path.abspath(source_dir)

    print("rpiPan Installer")
    print("=" * 50)
    print("  Platform:       {}".format(platform))
    print("  Source sounds:  {}".format(source_dir))
    print("  Convert to:     {} Hz, {}-bit, mono".format(
        target_rate, TARGET_SAMPWIDTH * 8))
    print("  Staging dir:    {}".format(converted_dir))
    if not convert_only and platform == "circuitpython":
        print("  Target drive:   {}".format(drive_path))
    print()

    # Convert samples (auto-downloads from urbanPan if source is incomplete)
    available, success = convert_samples(
        source_dir, converted_dir, layout_path, target_rate,
        dry_run=dry_run, force=force, no_download=no_download)

    if not success:
        return False

    if convert_only:
        print("\nConverted files in: {}".format(converted_dir))
        print("Done (--convert-only mode).")
        return True

    # Deploy based on platform
    if platform == "micropython":
        return stage_micropython(converted_dir, available, layout_path,
                                 dry_run=dry_run,
                                 max_sounds_bytes=max_sounds_bytes)
    else:
        return install_circuitpython(drive_path, converted_dir, available,
                                     layout_path, dry_run=dry_run)


# ---------------------------------------------------------------------------
# CircuitPython library installation
# ---------------------------------------------------------------------------

# Libraries required for I2S + ADS1115 mode
REQUIRED_LIBS = [
    "adafruit_ads1x15",
    "adafruit_bus_device",
]

BUNDLE_REPO = "adafruit/Adafruit_CircuitPython_Bundle"
BUNDLE_API_URL = "https://api.github.com/repos/{}/releases/latest".format(BUNDLE_REPO)


def detect_cp_version(drive_path):
    """Detect CircuitPython major version from boot_out.txt on the drive.

    Returns major version as int (e.g. 9), or None if not detected.
    """
    boot_out = os.path.join(drive_path, "boot_out.txt")
    if not os.path.isfile(boot_out):
        return None

    with open(boot_out, "r") as f:
        text = f.read()

    # Look for "CircuitPython X.Y.Z"
    for word in text.split():
        parts = word.split(".")
        if len(parts) >= 2:
            try:
                major = int(parts[0])
                int(parts[1])  # verify second part is also a number
                if 5 <= major <= 15:  # sanity check
                    return major
            except ValueError:
                continue
    return None


def try_circup(libs):
    """Try to install libraries using circup. Returns True if successful."""
    import subprocess

    try:
        subprocess.run(["circup", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

    print("Using circup to install libraries...")
    try:
        result = subprocess.run(
            ["circup", "install"] + libs,
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            return False
        return True
    except Exception as e:
        print("circup error: {}".format(e))
        return False


def download_bundle_libs(drive_path, cp_version, libs, dry_run=False):
    """Download Adafruit CircuitPython Bundle and extract required libraries.

    Uses the GitHub API to find the latest release, downloads the bundle
    zip, and extracts the specified libraries to CIRCUITPY/lib/.
    """
    if not HAS_URLLIB:
        print("ERROR: urllib not available. Install libraries manually.")
        return False

    bundle_tag = "{}x-mpy".format(cp_version)
    print("CircuitPython version: {} (bundle: {})".format(cp_version, bundle_tag))

    # Get latest release info from GitHub API
    print("Fetching latest bundle release...")
    try:
        req = Request(BUNDLE_API_URL, headers={"User-Agent": "rpiPan-installer"})
        resp = urlopen(req, timeout=30)
        release = json.loads(resp.read().decode())
    except Exception as e:
        print("ERROR: Could not fetch release info: {}".format(e))
        return False

    # Find the matching bundle asset
    target_name = None
    download_url = None
    for asset in release.get("assets", []):
        name = asset["name"]
        if bundle_tag in name and name.endswith(".zip"):
            target_name = name
            download_url = asset["browser_download_url"]
            break

    if not download_url:
        print("ERROR: No bundle found for CircuitPython {}".format(cp_version))
        print("Available assets:")
        for asset in release.get("assets", []):
            print("  {}".format(asset["name"]))
        return False

    print("Found: {}".format(target_name))

    if dry_run:
        print("Would download and extract: {}".format(", ".join(libs)))
        return True

    # Download the bundle zip
    print("Downloading ({})...".format(target_name))
    try:
        req = Request(download_url, headers={"User-Agent": "rpiPan-installer"})
        resp = urlopen(req, timeout=120)
        bundle_data = resp.read()
    except Exception as e:
        print("ERROR: Download failed: {}".format(e))
        return False

    print("Downloaded {:.1f} MB".format(len(bundle_data) / 1024 / 1024))

    # Extract required libraries to CIRCUITPY/lib/
    lib_dir = os.path.join(drive_path, "lib")
    os.makedirs(lib_dir, exist_ok=True)

    # Write zip to temp file, then extract
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(bundle_data)
        tmp_path = tmp.name

    try:
        extracted = 0
        with zipfile.ZipFile(tmp_path, "r") as zf:
            # Find the bundle prefix (e.g. "adafruit-circuitpython-bundle-9.x-mpy-20240101/lib/")
            prefix = None
            for name in zf.namelist():
                if "/lib/" in name:
                    prefix = name[:name.index("/lib/") + 5]
                    break

            if not prefix:
                print("ERROR: Could not find lib/ directory in bundle")
                return False

            for lib_name in libs:
                # Libraries can be directories (packages) or single .mpy files
                lib_prefix = prefix + lib_name
                found_files = [
                    n for n in zf.namelist()
                    if n.startswith(lib_prefix + "/") or n == lib_prefix + ".mpy"
                ]

                if not found_files:
                    print("  WARNING: {} not found in bundle".format(lib_name))
                    continue

                for zip_path in found_files:
                    # Strip the bundle prefix to get the relative path under lib/
                    rel_path = zip_path[len(prefix):]
                    if not rel_path or zip_path.endswith("/"):
                        # Directory entry — create it
                        dir_path = os.path.join(lib_dir, rel_path)
                        os.makedirs(dir_path, exist_ok=True)
                        continue

                    dst_path = os.path.join(lib_dir, rel_path)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

                    with zf.open(zip_path) as src_f:
                        with open(dst_path, "wb") as dst_f:
                            dst_f.write(src_f.read())
                    extracted += 1

                print("  Installed: {} ({} files)".format(
                    lib_name, len([f for f in found_files if not f.endswith("/")])))

        print("Extracted {} files to {}/".format(extracted, lib_dir))
        return True

    finally:
        os.unlink(tmp_path)


def install_libs(drive_path, dry_run=False):
    """Install required CircuitPython libraries to CIRCUITPY/lib/.

    Tries circup first, falls back to downloading the Adafruit Bundle.
    """
    print("\n--- Installing CircuitPython libraries ---")
    print("Required: {}".format(", ".join(REQUIRED_LIBS)))

    # Check if libraries already exist
    lib_dir = os.path.join(drive_path, "lib")
    all_present = True
    for lib_name in REQUIRED_LIBS:
        lib_path = os.path.join(lib_dir, lib_name)
        mpy_path = os.path.join(lib_dir, lib_name + ".mpy")
        if os.path.exists(lib_path) or os.path.exists(mpy_path):
            print("  Already installed: {}".format(lib_name))
        else:
            all_present = False
            print("  Missing: {}".format(lib_name))

    if all_present:
        print("All libraries already installed.")
        return True

    if dry_run:
        print("Would install missing libraries.")
        return True

    # Try circup first
    if try_circup(REQUIRED_LIBS):
        print("Libraries installed via circup.")
        return True

    print("circup not available, downloading from Adafruit Bundle...")

    # Detect CircuitPython version
    cp_version = detect_cp_version(drive_path)
    if cp_version is None:
        print("WARNING: Could not detect CircuitPython version from boot_out.txt")
        print("Assuming CircuitPython 9.x")
        cp_version = 9

    return download_bundle_libs(drive_path, cp_version, REQUIRED_LIBS, dry_run)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert and install rpiPan to a Raspberry Pi Pico"
    )
    parser.add_argument(
        "drive", nargs="?", default=DEFAULT_DRIVE,
        help="Path to CIRCUITPY drive (CircuitPython only, default: {})".format(
            DEFAULT_DRIVE),
    )
    parser.add_argument(
        "--platform", choices=["micropython", "circuitpython"],
        default="micropython",
        help="Target platform (default: micropython)",
    )
    parser.add_argument(
        "--source", default=DEFAULT_SOURCE,
        help="Path to source sounds directory (default: {})".format(
            DEFAULT_SOURCE),
    )
    parser.add_argument(
        "--rate", type=int, default=TARGET_RATE,
        help="Target sample rate in Hz (default: {})".format(TARGET_RATE),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--convert-only", action="store_true",
        help="Only convert WAV files, don't copy to drive",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-convert WAV files even if already converted",
    )
    parser.add_argument(
        "--libs", action="store_true",
        help="Install required CircuitPython libraries (adafruit_ads1x15, etc.)",
    )
    parser.add_argument(
        "--libs-only", action="store_true",
        help="Only install CircuitPython libraries, skip everything else",
    )
    parser.add_argument(
        "--max-sounds-mb", type=float, default=1.0,
        help="Max total size for WAV sounds in MB (default: 1.0)",
    )
    parser.add_argument(
        "--prepare-only", action="store_true",
        help="Only download/prepare source sounds, don't convert or deploy",
    )
    parser.add_argument(
        "--no-download", action="store_true",
        help="Skip downloading from urbanPan, use existing source files only",
    )

    args = parser.parse_args()

    # Handle --libs for MicroPython
    if args.platform == "micropython" and (args.libs or args.libs_only):
        print("MicroPython does not need external libraries.")
        print("The ADS1115 driver is built into main_mp.py.")
        if args.libs_only:
            sys.exit(0)

    # Install libraries only (CircuitPython)
    if args.libs_only:
        if not os.path.isdir(args.drive):
            print("ERROR: Drive not found: {}".format(args.drive))
            print("  Is the Pico connected and mounted?")
            sys.exit(1)
        success = install_libs(args.drive, dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    # Prepare source sounds only
    if args.prepare_only:
        layout_path = os.path.join(SCRIPT_DIR, "pan_layout.json")
        source_dir = os.path.abspath(args.source)
        prepared, stats = prepare_source_sounds(
            layout_path, source_dir, force=args.force, dry_run=args.dry_run,
            no_download=args.no_download)
        sys.exit(0 if prepared else 1)

    # Normal install (prepare + convert + deploy)
    success = install(
        drive_path=args.drive,
        source_dir=args.source,
        platform=args.platform,
        dry_run=args.dry_run,
        convert_only=args.convert_only,
        target_rate=args.rate,
        force=args.force,
        max_sounds_bytes=int(args.max_sounds_mb * 1024 * 1024),
        no_download=args.no_download,
    )

    # Install CircuitPython libraries if requested
    if (success and args.libs and not args.convert_only
            and args.platform == "circuitpython"):
        if os.path.isdir(args.drive):
            install_libs(args.drive, dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
