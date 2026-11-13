#!/usr/bin/env python3
"""Stop the USB bring-up from sitting in long metronome stalls.

gBS->Stall () is a busy wait: it dispatches no events, so while the firmware sits
in those two-second pauses the vendor USB driver cannot answer the host's control
requests. A host that times out during a port reset does not retry, and the
device stays invisible for the rest of the boot - which is exactly the flaky
"sometimes 10 s, usually never" behaviour on this board.

The pauses only existed so the console lines could be read; 20 ms is enough to
keep them ordered.

usage: prepare-piano-fastboot-usb-timing.py <uefi-checkout>
"""
import argparse
import pathlib
import sys

TARGET = "uefi/pianoPkg/Library/DeviceBootManagerLib/PianoFastboot.c"

PAIRS = [
    ("  gBS->Stall (500000);\n", "  gBS->Stall (20000);\n"),
    ("  gBS->Stall (2000000);\n", "  gBS->Stall (20000);\n"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="checkout of the uefi repository")
    args = parser.parse_args()

    path = pathlib.Path(args.root) / TARGET
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if "gBS->Stall (2000000);" not in text and "gBS->Stall (500000);" not in text:
        print(f"  {path}: already patched")
        return 0

    changed = 0
    for old, new in PAIRS:
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            changed += n
            print(f"  {path}: {n} x {old.strip()} -> {new.strip()}")

    if not changed:
        print("  !! no stall site found", file=sys.stderr)
        return 1
    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    return 0


if __name__ == "__main__":
    sys.exit(main())