#!/usr/bin/env python3
"""Adopt the firmware's request list without touching the SMMU.

The guarded bypass probe proved the point the hard way: the board resets before
the panic line can draw, so the S2CR write itself is what kills this SoC - not
the request-list fetch. Even the architectural bypass value (TYPE 2) is refused.

So this build does the opposite: leave SMR/S2CR/CB exactly as the ABL left
them and send the first command from the 16 KiB request list the firmware
already owns, which is the one region its DMA is known to reach. The result
states whether an untouched SMMU plus the firmware's list is enough.

usage: prepare-shengufs-adopt-nosmmu.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import sys

CALL = "  smmuBypassStream (0x60, smmuMap, smmuReport, phys, 16384);\n"

REPLACEMENT = """  //
  // The SMMU is left exactly as the firmware left it. Writing S2CR on this part
  // - even to the architectural bypass value - resets the SoC before the panic
  // screen can draw, so the stream keeps the ABL's mapping and the command goes
  // out from the request list the firmware already owns.
  //
  (void)smmuMap;
  (void)smmuReport;
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "left exactly as the firmware left it" in text:
            print(f"  {path}: already patched")
            patched += 1
            continue
        if CALL not in text:
            print(f"  !! {path}: adopt call site not found", file=sys.stderr)
            continue
        path.write_text(text.replace(CALL, REPLACEMENT, 1))
        patched += 1
        print(f"  {path}: SMMU left untouched in adopt mode")

    if not patched:
        print("  !! no NativeUfs.cpp patched", file=sys.stderr)
        return 1
    print(f"adopt no-smmu: {patched} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
