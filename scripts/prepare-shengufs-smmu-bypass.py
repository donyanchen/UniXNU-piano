#!/usr/bin/env python3
"""Put the UFS stream in real bypass.

smmuBypassStream () writes S2CR = bank, which is TYPE 0 = stage-2 translation,
and it only does so when the stream-match entry is new. On this board the ABL
already mapped stream 0x60, so the entry is reused and S2CR keeps whatever the
bootloader left. The panic shows s2cr=0x52 - translation - and the controller
then never fetches our request descriptor: doorbell set, IS clear, ocs=0x0f.

The DMA buffers are physical, so bypass (TYPE 2) is the correct setting; write it
unconditionally.

usage: prepare-shengufs-smmu-bypass.py <build tree root>
"""
import argparse
import pathlib
import sys

OLD = """  if (!p.reuse) {
    write(0xc00 + 4 * p.slot, p.bank);
    if (read(0xc00 + 4 * p.slot) != p.bank) return "SMMU stream context readback";"""

NEW = """  {
    //
    // Bypass, unconditionally. TYPE 0 is stage-2 translation; the controller
    // never fetches a request descriptor through it (doorbell set, IS clear).
    // The transfer buffers are physical, so no translation is needed at all.
    //
    write(0xc00 + 4 * p.slot, (2U << 16));
    if (read(0xc00 + 4 * p.slot) != (2U << 16)) return "SMMU stream context readback";"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args()
    patched = 0
    for path in pathlib.Path(args.root).rglob("SmmuTakeover.h"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "no translation is needed at all" in text:
            continue
        if OLD not in text:
            print(f"  !! {path}: anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD, NEW, 1))
        patched += 1
        print(f"  {path}: UFS stream forced to bypass")
    if not patched:
        print("  !! bypass not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
