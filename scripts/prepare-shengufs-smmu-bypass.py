#!/usr/bin/env python3
"""Put the UFS stream in real bypass, whatever the planner wrote before.

smmuBypassStream () writes S2CR = bank, which is TYPE 0 = stage-2 translation,
and it only does so when the stream-match entry is new. On this board the ABL
already mapped stream 0x60, so the entry is reused and S2CR keeps whatever the
bootloader left. The panic shows s2cr=0x52 - translation - and the controller
then never fetches our request descriptor: doorbell set, IS clear, ocs=0x0f.

The transfer buffers are physical, so bypass (TYPE 2) is correct. Rewrite the
S2CR value on sight instead of anchoring on a whole block, because
prepare-shengufs-smmu-upstream.py reshapes that code.

usage: prepare-shengufs-smmu-bypass.py <build tree root>
"""
import argparse
import pathlib
import re
import sys

WRITE = re.compile(r'write\(0xc00 \+ 4 \* p\.slot, [^)]*\);')
CHECK = re.compile(r'read\(0xc00 \+ 4 \* p\.slot\) != [^;]*;')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args()
    patched = 0
    for path in pathlib.Path(args.root).rglob("SmmuTakeover.h"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "(2U << 16)" in text:
            continue
        text, n1 = re.subn(r'write\(0xc00 \+ 4 \* p\.slot, p\.bank\);',
                           'write(0xc00 + 4 * p.slot, (2U << 16));   // TYPE 2: bypass', text)
        text, n2 = re.subn(r'!= p\.bank\)', '!= (2U << 16))', text)
        # the entry is already valid on this board, so the reuse guard would
        # skip the rewrite and leave S2CR as the bootloader set it
        text = text.replace("  if (!p.reuse) {\n    write(0xc00 + 4 * p.slot, (2U << 16));",
                            "  if (p.reuse || (p.slot != 0xffffffffU && p.slot < 128)) {\n    write(0xc00 + 4 * p.slot, (2U << 16));", 1)
        # the closing verification reads the same register: it must not touch an
        # invalid slot either
        text = text.replace("  if (read(0x800 + 4 * p.slot) != (0x80000000U | stream) ||",
                            "  if (p.slot == 0xffffffffU || p.slot >= 128) return \"no stream-match slot\";\n  if (read(0x800 + 4 * p.slot) != (0x80000000U | stream) ||", 1)
        if not (n1 and n2):
            print(f"  !! {path}: write={n1} check={n2}", file=sys.stderr)
            continue
        path.write_text(text)
        patched += 1
        print(f"  {path}: UFS stream forced to bypass ({n1} write, {n2} check)")
    if not patched:
        print("  !! bypass not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
