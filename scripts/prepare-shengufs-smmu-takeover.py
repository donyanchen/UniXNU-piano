#!/usr/bin/env python3
"""Let the ShengUfs SMMU planner take over a stale, exclusive stream entry.

On piano the SMMU is still configured by the previous OS when XNU starts: SID
0x60 already has an SMR entry (mask 0, so no other SID can share it) pointing at
a translating context bank. The shipped planner treats any match that is not
already on its own bank as a conflict and refuses to boot, even though the entry
belongs to this stream alone and the page tables behind it are gone.

Linux handles the same firmware state through arm_smmu_write_sme: disable the
SME (SMR), write S2CR, re-enable it. This patch lets the planner keep such a
slot (reuse stays false, so the writer invalidates SMR first) and adds the raw
IDR/SCR reads to the failure panic so a bad read can be told apart from a real
geometry refusal.

SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import sys

# SmmuTakeover.h: the planner's match branch.
OLD_MATCH = """    if (match) {
      ++matches;
      if (matches > 1 || mask || !ourBank) {
        p.slot = i; p.smr = smr; p.s2cr = s2cr;
        p.error = "conflicting UFS stream mapping"; return p;
      }
      p.reuse = true; p.slot = i;
    } else if (ourBank) {"""

NEW_MATCH = """    if (match) {
      ++matches;
      if (matches > 1 || mask) {
        p.slot = i; p.smr = smr; p.s2cr = s2cr;
        p.error = "conflicting UFS stream mapping"; return p;
      }
      // The mask is zero, so this entry is this stream's alone: a previous OS
      // pointed it at another bank and those page tables are gone. Keep the
      // slot and leave reuse false, so the writer invalidates SMR before it
      // touches S2CR (the order arm_smmu_write_sme uses).
      p.slot = i;
      if (ourBank) { p.reuse = true; }
    } else if (ourBank) {"""

# SmmuTakeover.h: the writer, SMR must go invalid before S2CR changes.
OLD_WRITE = """  if (!p.reuse) {
    write(0xc00 + 4 * p.slot, p.bank);"""

NEW_WRITE = """  if (!p.reuse) {
    // A stale entry can still be valid here; ARM's update order is SMR off,
    // S2CR, SMR on.
    write(0x800 + 4 * p.slot, 0);
    write(0xc00 + 4 * p.slot, p.bank);"""

# NativeUfs.cpp: the refusal must carry the registers it decided on.
OLD_PANIC = """    panic ("NATIVE_UFS smmu: %s slot=%u smr=%x s2cr=%x", plan.error, plan.slot, plan.smr, plan.s2cr);"""

NEW_PANIC = """    panic ("NATIVE_UFS smmu: %s slot=%u smr=%x s2cr=%x idr0=%x idr1=%x idr2=%x scr0=%x",
           plan.error, plan.slot, plan.smr, plan.s2cr,
           read32 (smmu, 0x20), read32 (smmu, 0x24), read32 (smmu, 0x28), read32 (smmu, 0x00));"""

EDITS = {
    "SmmuTakeover.h": [(OLD_MATCH, NEW_MATCH), (OLD_WRITE, NEW_WRITE)],
    "NativeUfs.cpp": [(OLD_PANIC, NEW_PANIC)],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    total = 0
    for name, pairs in EDITS.items():
        found = 0
        for path in pathlib.Path(args.root).rglob(name):
            text = path.read_text()
            for old, new in pairs:
                if old not in text:
                    continue
                text = text.replace(old, new, 1)
                found += 1
                total += 1
            path.write_text(text)
        print(f"  {name}: {found} edit(s)")
        if found == 0:
            print(f"  !! {name} was not patched under {args.root}", file=sys.stderr)
            return 1
    print(f"smmu takeover: {total} edit(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
