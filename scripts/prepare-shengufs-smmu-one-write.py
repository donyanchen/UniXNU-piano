#!/usr/bin/env python3
"""Write exactly one SMMU register: the stream-match entry, in bypass.

The board resets when the UFS stream is configured, but the step that kills it
has never been isolated. configureUfsSmmu() writes SMR, S2CR, CBAR, TTBA2R,
TTBR0/1, TCR and SCTLR; the probe build that reported "writes survived" only
looked safe because plan.reuse was true and the planner therefore wrote nothing
at all (the SMR read back valid, 0x80000060).

So this build performs the smallest change that can make the controller's DMA
reachable: S2CR <- type 2 (bypass) for the planned slot. Bypass makes the
controller's own physical addresses the ones the SMMU uses, which is what the
driver assumes everywhere else, and nothing else in the SMMU is touched.

The readback in smmuBypassStream still prints s2cr, so the next screen states
whether the write landed and whether the board survived it:

    s2cr=00020000  bypass taken, and the board is alive
    s2cr=00000052  the write was dropped
    no screen      the single S2CR write itself resets this part

usage: prepare-shengufs-smmu-one-write.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "Only the stream match entry is written"

OLD = """  const char *failure = configureUfsSmmu (plan, stream,
    [smmu](unsigned offset) { return read32 (smmu, offset); },
    [smmu](unsigned offset, uint32_t value) {
      write32 (smmu, offset, value);
      __asm__ volatile ("dsb sy" ::: "memory");
    });"""

NEW = """  // Only the stream match entry is written: bypass, so the controller's own
  // physical addresses are what the SMMU uses. Nothing else in the SMMU is
  // touched, because the build that wrote the whole plan reset the board and
  // the fatal step was never isolated.
  write32 (smmu, 0xc00 + 4 * index, (2U << 16));
  __asm__ volatile ("dsb sy" ::: "memory");
  const char *failure = nullptr;"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if MARKER in text:
            print(f"  {path}: already patched")
            patched += 1
            continue
        if OLD not in text:
            print(f"  !! {path}: configureUfsSmmu call not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD, NEW, 1))
        patched += 1
        print(f"  {path}: one S2CR write, bypass only")

    if not patched:
        print("  !! NativeUfs.cpp not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
