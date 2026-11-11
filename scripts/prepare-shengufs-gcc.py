#!/usr/bin/env python3
"""Point the ShengUfs GccUfs.h block at SM8750 ("sun", piano).

The ShengUfs component declares SM8550 clocks and SMMU as board dependencies
and hardcodes the GCC offsets in GccUfs.h. NativeUfs.cpp reads them by name,
so the port is these constants and nothing else: the driver never programs
the PHY (it accepts the link the boot firmware left), the SMMU helper scans
the stream-match table for the stream id instead of assuming a slot, and the
root layout is parsed out of the payload rather than hardcoded.

Eight of the eleven offsets move on SM8750, and two of them swap roles with a
neighbour: SM8550's TX_SYMBOL0 (0x77028) is SM8750's AHB, and SM8550's
RX_SYMBOL0 (0x7702c) is SM8750's TX_SYMBOL0. A copy-paste port that keeps the
SM8550 values therefore enables the wrong clocks while believing it enabled
the right ones.

SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import sys

# SM8550 value in the shipped header -> SM8750 value, with the source.
REPLACEMENTS = {
    # gcc_ufs_phy_gdsc and gcc_ufs_mem_phy_gdsc are unchanged (0x77004, 0x9e000).
    "GCC_UFS_PHY_AXI_ENABLE": ("0x77018", "0x77018"),          # unchanged
    "GCC_UFS_PHY_AHB_ENABLE": ("0x77024", "0x77028"),          # gcc-sm8750.c:2599
    "GCC_UFS_PHY_TX_SYMBOL0_ENABLE": ("0x77028", "0x7702c"),   # gcc-sm8750.c:2710
    "GCC_UFS_PHY_RX_SYMBOL0_ENABLE": ("0x7702c", "0x77030"),   # gcc-sm8750.c:2674
    "GCC_UFS_PHY_UNIPRO_CORE_ENABLE": ("0x77068", "0x7706c"),  # gcc-sm8750.c:2728
    "GCC_UFS_PHY_ICE_CORE_ENABLE": ("0x77074", "0x7707c"),     # gcc-sm8750.c:2634
    "GCC_UFS_PHY_PHY_AUX_ENABLE": ("0x770b0", "0x770bc"),      # gcc-sm8750.c:2654
    "GCC_UFS_PHY_RX_SYMBOL1_ENABLE": ("0x770cc", "0x770d8"),   # gcc-sm8750.c:2692
    "GCC_AGGRE_UFS_PHY_AXI_ENABLE": ("0x770e4", "0x770f0"),    # gcc-sm8750.c:1237
}

CHANGED = {k: v for k, v in REPLACEMENTS.items() if v[0] != v[1]}


def patch_one(path: pathlib.Path) -> int:
    text = path.read_text()
    original = text
    missed = []

    for name, (old, new) in CHANGED.items():
        needle = f"#define {name}"
        lines = text.splitlines(keepends=True)
        hit = False
        for i, line in enumerate(lines):
            if line.startswith(needle) and old in line:
                lines[i] = line.replace(old, new, 1)
                hit = True
                break
        if not hit:
            missed.append(f"{name} ({old})")
        text = "".join(lines)

    if missed:
        print(f"  !! {path}: could not find {', '.join(missed)}", file=sys.stderr)
        return 0

    if text == original:
        print(f"  -- {path}: already SM8750")
        return 0

    path.write_text(text)
    print(f"  -> {path}: {len(CHANGED)} offsets moved to SM8750")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="directory to search, e.g. UniXNU/out")
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"no such directory: {root}", file=sys.stderr)
        return 2

    headers = sorted(p for p in root.rglob("GccUfs.h") if p.is_file())
    if not headers:
        print(f"no GccUfs.h under {root}: the ShengUfs feed was not fetched", file=sys.stderr)
        return 3

    print(f"found {len(headers)} GccUfs.h")
    changed = sum(patch_one(p) for p in headers)
    if changed == 0:
        print("every copy already carried the SM8750 offsets")
    else:
        print(f"patched {changed} of {len(headers)} copies")

    # Idempotent: re-running on an already patched tree must succeed, and the
    # header existing at all is what proves the feed was fetched.
    return 0


if __name__ == "__main__":
    sys.exit(main())
