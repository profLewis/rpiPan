#!/usr/bin/env python3
"""
install.py - Convert WAV samples and install rpiPan to a Pico CIRCUITPY drive.

Converts panipuri's 44100 Hz stereo WAV files to 16-bit mono 22050 Hz
(suitable for CircuitPython audiomixer), then copies code.py, pan_layout.json,
and the converted sounds/ to the target drive.

Usage:
    python install.py                          # Uses /Volumes/CIRCUITPY
    python install.py /Volumes/CIRCUITPY       # Explicit drive path
    python install.py /Volumes/CIRCUITPY --source ../panipuri/sounds
    python install.py --dry-run                # Show what would be done
    python install.py --convert-only           # Just convert, don't copy to drive
"""

import os
import sys
import json
import wave
import struct
import shutil
import argparse

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

DEFAULT_SOURCE = os.path.join(SCRIPT_DIR, "..", "panipuri", "sounds")

# Target sample rate for Pico (22050 Hz mono is a good balance of
# quality vs. CPU/RAM on the RP2040)
TARGET_RATE = 22050
TARGET_CHANNELS = 1
TARGET_SAMPWIDTH = 2  # 16-bit


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

def install(drive_path, source_dir, dry_run=False, convert_only=False,
            target_rate=TARGET_RATE, force=False):
    """Convert samples and install to CIRCUITPY drive."""

    layout_path = os.path.join(SCRIPT_DIR, "pan_layout.json")
    code_path = os.path.join(SCRIPT_DIR, "code.py")
    converted_dir = os.path.join(SCRIPT_DIR, "sounds_converted")

    # Resolve source directory
    source_dir = os.path.abspath(source_dir)

    print("rpiPan Installer")
    print("=" * 50)
    print("  Source sounds:  {}".format(source_dir))
    print("  Convert to:     {} Hz, {}-bit, mono".format(
        target_rate, TARGET_SAMPWIDTH * 8))
    print("  Staging dir:    {}".format(converted_dir))
    if not convert_only:
        print("  Target drive:   {}".format(drive_path))
    print()

    # Validate source
    if not os.path.isdir(source_dir):
        print("ERROR: Source sounds directory not found: {}".format(source_dir))
        print("  Specify with --source, e.g.:")
        print("    python install.py --source /path/to/panipuri/sounds")
        return False

    # Validate layout
    if not os.path.isfile(layout_path):
        print("ERROR: pan_layout.json not found in {}".format(SCRIPT_DIR))
        return False

    # Get list of needed WAV files from layout
    needed = get_needed_files(layout_path)
    print("Notes in layout: {} WAV files needed".format(len(needed)))

    # Check which source files exist
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
        return False

    # Convert WAV files
    print("--- Converting samples ---")
    if not dry_run:
        os.makedirs(converted_dir, exist_ok=True)

    converted = 0
    skipped = 0
    errors = 0

    for fname in available:
        src = os.path.join(source_dir, fname)
        dst = os.path.join(converted_dir, fname)

        # Skip if already converted and not forcing
        if os.path.isfile(dst) and not force:
            src_mtime = os.path.getmtime(src)
            dst_mtime = os.path.getmtime(dst)
            if dst_mtime >= src_mtime:
                skipped += 1
                continue

        src_size = os.path.getsize(src) / 1024
        if dry_run:
            print("  Would convert: {} ({:.0f} KB)".format(fname, src_size))
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

    if convert_only:
        print("\nConverted files in: {}".format(converted_dir))
        print("Done (--convert-only mode).")
        return True

    # Validate target drive
    if not os.path.isdir(drive_path):
        print("\nERROR: Drive not found: {}".format(drive_path))
        print("  Is the Pico connected and mounted?")
        print("  Specify drive path: python install.py /path/to/CIRCUITPY")
        return False

    # Copy files to drive
    print("\n--- Installing to {} ---".format(drive_path))

    # 1. Copy code.py
    dst = os.path.join(drive_path, "code.py")
    if dry_run:
        print("  Would copy: code.py")
    else:
        shutil.copy2(code_path, dst)
        print("  code.py ({:.0f} KB)".format(os.path.getsize(dst) / 1024))

    # 2. Copy pan_layout.json
    dst = os.path.join(drive_path, "pan_layout.json")
    if dry_run:
        print("  Would copy: pan_layout.json")
    else:
        shutil.copy2(layout_path, dst)
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
            shutil.copy2(src, dst)
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert and install rpiPan to a Pico CIRCUITPY drive"
    )
    parser.add_argument(
        "drive", nargs="?", default=DEFAULT_DRIVE,
        help="Path to CIRCUITPY drive (default: {})".format(DEFAULT_DRIVE),
    )
    parser.add_argument(
        "--source", default=DEFAULT_SOURCE,
        help="Path to panipuri sounds/ directory (default: {})".format(
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

    args = parser.parse_args()

    success = install(
        drive_path=args.drive,
        source_dir=args.source,
        dry_run=args.dry_run,
        convert_only=args.convert_only,
        target_rate=args.rate,
        force=args.force,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
