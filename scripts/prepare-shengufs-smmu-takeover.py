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

# SmmuTakeover.h: the planner's window must hold the last context bank too.
# idr1 read on the device is 0x60000053: NUMCB 83, NUMPAGENDXB 6, so the bank
# array starts at 0x80000 and CB82 ends at 0xD3000, past the old 0xD0000.
OLD_GEOM = """      (p.pages + banks) * 4096 > 0xd0000) {"""
NEW_GEOM = """      (p.pages + banks) * 4096 > 0x200000) {"""

# NativeUfs.cpp: the bypass mapping and the context-bank survey both map the
# register block, and the survey has its own copy of the same guard.
OLD_MAP = """mapPhys (0x15000000ULL, 0xd0000"""
NEW_MAP = """mapPhys (0x15000000ULL, 0x200000"""
OLD_SURVEY = """(globalPages + numCb) * 0x1000 > 0xd0000"""
NEW_SURVEY = """(globalPages + numCb) * 0x1000 > 0x200000"""

# NativeUfs.cpp: the refusal must carry the registers it decided on.
OLD_PANIC = """    panic ("NATIVE_UFS smmu: %s slot=%u smr=%x s2cr=%x", plan.error, plan.slot, plan.smr, plan.s2cr);"""

NEW_PANIC = """    panic ("NATIVE_UFS smmu: %s slot=%u smr=%x s2cr=%x idr0=%x idr1=%x idr2=%x scr0=%x",
           plan.error, plan.slot, plan.smr, plan.s2cr,
           read32 (smmu, 0x20), read32 (smmu, 0x24), read32 (smmu, 0x28), read32 (smmu, 0x00));"""

# (old, new, replace-every-occurrence). The bypass path and the context-bank
# survey map the same block with different variable names, so the map fix has
# to hit both.
EDITS = {
    "SmmuTakeover.h": [(OLD_MATCH, NEW_MATCH, False), (OLD_WRITE, NEW_WRITE, False),
                       (OLD_GEOM, NEW_GEOM, False)],
    "NativeUfs.cpp": [(OLD_PANIC, NEW_PANIC, False), (OLD_MAP, NEW_MAP, True),
                      (OLD_SURVEY, NEW_SURVEY, False)],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    touched = []
    total = 0
    for name, pairs in EDITS.items():
        found = 0
        for path in pathlib.Path(args.root).rglob(name):
            text = path.read_text()
            changed = False
            for old, new, everywhere in pairs:
                if old not in text:
                    continue
                hits = text.count(old)
                text = text.replace(old, new) if everywhere else text.replace(old, new, 1)
                found += hits
                total += hits
                changed = True
            if changed:
                path.write_text(text)
                touched.append((path, pairs))
        print(f"  {name}: {found} edit(s)")
        if found == 0:
            print(f"  !! {name} was not patched under {args.root}", file=sys.stderr)
            return 1

    # The tree also carries the SM8750 platform kit's refactored copy of these
    # files; it takes the window as a parameter and is not what this driver
    # compiles. Verify only the files that were actually rewritten: every old
    # string must be gone from them.
    for path, pairs in touched:
        text = path.read_text()
        for old, _, _ in pairs:
            if old in text:
                print(f"  !! {path}: still contains {old.splitlines()[0][:60]!r}", file=sys.stderr)
                return 1
    print(f"smmu takeover: {total} edit(s) verified in {len(touched)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
