"""
diskinfo_mp.py - List free disk space and file sizes (MicroPython).

Copy to Pico and run via Thonny (F5) or:
    mpremote run diskinfo_mp.py
"""

import os


def fmt_size(b):
    """Format byte count as human-readable string."""
    if b < 1024:
        return "{} B".format(b)
    if b < 1024 * 1024:
        return "{:.1f} KB".format(b / 1024)
    return "{:.2f} MB".format(b / 1024 / 1024)


def disk_info(path="/"):
    """Print filesystem usage for the given mount point."""
    st = os.statvfs(path)
    block_size = st[0]
    total_blocks = st[2]
    free_blocks = st[3]
    total = block_size * total_blocks
    free = block_size * free_blocks
    used = total - free
    pct = (used * 100) // total if total else 0
    print("Filesystem: {}".format(path))
    print("  Total:  {}".format(fmt_size(total)))
    print("  Used:   {} ({}%)".format(fmt_size(used), pct))
    print("  Free:   {} ({}%)".format(fmt_size(free), 100 - pct))
    return total, used, free


def list_files(path="/", indent=0):
    """Recursively list files and directories with sizes."""
    total = 0
    prefix = "  " * indent
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        return 0

    for name in entries:
        full = path.rstrip("/") + "/" + name
        try:
            st = os.stat(full)
        except OSError:
            continue
        is_dir = st[0] & 0x4000
        if is_dir:
            print("{}{}/".format(prefix, name))
            sub = list_files(full, indent + 1)
            print("{}  ({})".format(prefix, fmt_size(sub)))
            total += sub
        else:
            size = st[6]
            print("{}{:30s}  {}".format(prefix, name, fmt_size(size)))
            total += size

    return total


def main():
    print("=" * 50)
    disk_info("/")
    print()
    print("Files:")
    print("-" * 50)
    file_total = list_files("/")
    print("-" * 50)
    print("Total file size: {}".format(fmt_size(file_total)))
    print("=" * 50)


main()
