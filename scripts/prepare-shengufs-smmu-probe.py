#!/usr/bin/env python3
"""Temporary bisect probe: prove whether the SMMU write path survives.

The kernel now gets past the geometry guard and the device resets a few seconds
after the handoff instead of parking on the panic screen. Two very different
faults look like that: the context-bank writes hit something the XPU/TZ owns
and reset the SoC, or the writes succeed and something later hangs until the
watchdog fires. A panic right after the bypass call separates them: if the
message appears, the writes were fine and the fault is downstream; if the board
resets with no message, the writes themselves are the fault.

Remove this probe once the question is answered.

SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import sys

OLD = """  smmuBypassStream (0x60, gHost.smmuMap, report, gHost.phys, kDmaBytes);
"""

NEW = """  smmuBypassStream (0x60, gHost.smmuMap, report, gHost.phys, kDmaBytes);
  // Bisect probe: stop here so the screen states whether the bank writes survived.
  panic ("NATIVE_UFS smmu: bypass done slot=%u bank=%u cbar=%x sctlr=%x",
         report[0] & 0xffff, report[0] >> 16, report[1], report[2]);
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        text = path.read_text()
        if "Bisect probe" in text:
            continue
        if OLD not in text:
            print(f"  !! {path}: bypass call site not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD, NEW, 1))
        patched += 1
        print(f"  {path}: probe inserted")
    if patched == 0:
        print(f"  !! no NativeUfs.cpp patched under {args.root}", file=sys.stderr)
        return 1
    print(f"smmu probe: {patched} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
