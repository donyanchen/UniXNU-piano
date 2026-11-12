#!/usr/bin/env python3
"""Adopt the upstream SM8750 SMMU planner, then adapt it to this board's handoff.

Upstream ships two flavours of the same file. The ShengUfs driver's own copy is
the SM8550 one: 0xd0000 window, no SM8750 branch. The SM8750 support lives in
the SoC kit (kits/Sm8750Platform/SmmuTakeover.h) behind NATIVE_UFS_SM8750 and
buys two things this board needs:

  * kUfsSmmuMapBytes = 0x100000, matching sm8750.dtsi
    (reg = <0 0x15000000 0 0x100000>); Piano's own device tree was trimmed to
    0x1000, which is why the old 0xd0000 budget rejected 83 banks at 128 pages.
  * the SM8750 usable-stream rule and p.reuse = ourBank.

Two differences remain, and both come from the device rather than the code:

  * piano's Android leaves SID 0x60 on bank 1 with S2CR 0x00000001, while the
    PKX110 firmware upstream tuned for leaves S2CR 0, so accept any exclusive
    (mask 0) entry instead of only the zero one.
  * a takeover rewrites an entry that is still valid, so SMR must go invalid
    before S2CR changes (arm_smmu_write_sme order).

Also widens the two mapPhys calls and the survey guard in NativeUfs.cpp, and
keeps the IDR reads in the refusal panic.

SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import sys

VENDOR = pathlib.Path(__file__).resolve().parent / "vendor" / "SmmuTakeover-sm8750.h"
DEFINE = "#ifndef NATIVE_UFS_SM8750\n#define NATIVE_UFS_SM8750 1\n#endif\n"

USABLE_OLD = """      usable = usable || (stream == 0x60 && s2cr == 0);
#endif
"""
USABLE_NEW = """      usable = usable || (stream == 0x60 && s2cr == 0);
#endif
      // piano: the previous OS left SID 0x60 on bank 1 (S2CR 0x00000001), not
      // on bank 0 as PKX110 does. An entry with a zero mask belongs to this
      // stream alone, so taking it over is safe.
      usable = usable || (mask == 0);
"""

WRITE_OLD = """  if (!p.reuse) {
    write(0xc00 + 4 * p.slot, p.bank);"""
WRITE_NEW = """  if (!p.reuse) {
    // A takeover rewrites a still-valid entry; ARM's order is SMR off, S2CR,
    // SMR on.
    write(0x800 + 4 * p.slot, 0);
    write(0xc00 + 4 * p.slot, p.bank);"""

MAP_OLD = "mapPhys (0x15000000ULL, 0xd0000"
MAP_NEW = "mapPhys (0x15000000ULL, 0x200000"
SURVEY_OLD = "(globalPages + numCb) * 0x1000 > 0xd0000"
SURVEY_NEW = "(globalPages + numCb) * 0x1000 > 0x200000"

PANIC_OLD = """    panic ("NATIVE_UFS smmu: %s slot=%u smr=%x s2cr=%x", plan.error, plan.slot, plan.smr, plan.s2cr);"""
PANIC_NEW = """    panic ("NATIVE_UFS smmu: %s slot=%u smr=%x s2cr=%x idr0=%x idr1=%x idr2=%x scr0=%x",
           plan.error, plan.slot, plan.smr, plan.s2cr,
           read32 (smmu, 0x20), read32 (smmu, 0x24), read32 (smmu, 0x28), read32 (smmu, 0x00));"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()
    root = pathlib.Path(args.root)

    vendor = VENDOR.read_text()
    headers = 0
    for path in root.rglob("SmmuTakeover.h"):
        if "ShengUfs" not in str(path):
            continue
        text = DEFINE + vendor
        if USABLE_OLD not in text or WRITE_OLD not in text:
            print(f"  !! {path}: vendored file drifted from the expected shape", file=sys.stderr)
            return 1
        text = text.replace(USABLE_OLD, USABLE_NEW, 1).replace(WRITE_OLD, WRITE_NEW, 1)
        path.write_text(text)
        headers += 1
        print(f"  {path}: upstream SM8750 planner installed")

    sources = 0
    for path in root.rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        before = text
        text = text.replace(MAP_OLD, MAP_NEW)
        text = text.replace(SURVEY_OLD, SURVEY_NEW)
        text = text.replace(PANIC_OLD, PANIC_NEW, 1)
        if text == before:
            print(f"  ?? {path}: nothing to change (already patched?)")
        else:
            path.write_text(text)
        sources += 1
        print(f"  {path}: map window 0x200000, panic carries idr")

    if headers == 0 or sources == 0:
        print("  !! ShengUfs headers or sources not found", file=sys.stderr)
        return 1
    print(f"smmu upstream: {headers} header(s), {sources} source(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
