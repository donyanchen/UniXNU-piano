#!/usr/bin/env python3
"""Bisect probe: stop the boot right after the SMMU bypass write.

Two very different faults both look like "the board resets when xnu is picked":

  * the context-bank / S2CR writes hit something the XPU or TZ owns and reset
    the SoC before anything can be printed; or
  * the writes land, the queue starts, and the controller's fetch of the
    request list faults (a kernel-allocated buffer at 0xf080f000 did exactly
    that once), which also ends in a reset.

A panic between the two separates them: if the screen shows this message, the
writes survived and the fault is downstream; if the board resets with no
message, the writes themselves are the fault.

The call site moved between ShengUfs revisions - the pinned feed passes
kDmaBytes, a newer tree passes gHost.dmaBytes - so the probe matches the shape
instead of one exact line.

Remove the probe once the question is answered.

usage: prepare-shengufs-smmu-probe.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import re
import sys

CALL = re.compile(r"^(?P<ind>[ \t]*)smmuBypassStream \(0x60, gHost\.smmuMap, report, "
                  r"gHost\.phys, [^)]*\);[ \t]*\r?\n", re.M)


def probe_text(indent: str) -> str:
    inner = indent + "  "
    return (
        f"{indent}// Bisect probe: the SMMU writes landed if this line reaches the screen.\n"
        f"{indent}{{\n"
        f"{inner}uintptr_t smmuBase = gHost.smmuMap->getVirtualAddress ();\n"
        f"{inner}unsigned probeSlot = report[0] & 0xffffU, probeBank = report[0] >> 16;\n"
        f'{inner}panic ("NATIVE_UFS smmu: writes survived slot=%u bank=%u cbar=%x sctlr=%x\\n"\n'
        f'{inner}       "smr=%08x s2cr=%08x scr0=%08x dma=%llx utrlba=%08x",\n'
        f"{inner}       probeSlot, probeBank, report[1], report[2],\n"
        f"{inner}       read32 (smmuBase, 0x800 + 4 * probeSlot), read32 (smmuBase, 0xc00 + 4 * probeSlot),\n"
        f"{inner}       read32 (smmuBase, 0x00), (unsigned long long)gHost.phys, read32 (gHost.hc, 0x50));\n"
        f"{indent}}}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "writes survived" in text:
            print(f"  {path}: probe already present")
            patched += 1
            continue
        m = CALL.search(text)
        if not m:
            print(f"  !! {path}: bypass call site not found", file=sys.stderr)
            continue
        text = text[:m.end()] + probe_text(m.group("ind")) + text[m.end():]
        path.write_text(text)
        patched += 1
        print(f"  {path}: probe inserted after the bypass call")

    if not patched:
        print("  !! no NativeUfs.cpp patched", file=sys.stderr)
        return 1
    print(f"smmu probe: {patched} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
