#!/usr/bin/env python3
"""Leave the SMMU alone entirely; firmware now sets the UFS stream to bypass.

Firmware's PianoSmmuUfsBypass() (patches/uefi/piano-smmu-ufs-bypass.patch) puts
stream 0x60 in bypass before the OS starts, which is what makes the controller's
own physical addresses reach memory. From the kernel there is nothing to do:

  * any S2CR write resets this part, and a single-register experiment confirmed
    that it is the write itself, not the rest of the plan;
  * configureUfsSmmu() also touches SMR, CBAR, CBA2R, TTBR0/1, TCR and SCTLR,
    all of which belong to a context bank firmware may still be using.

So smmuBypassStream() keeps its mapping (the fault registers are read from it
later) and performs no store at all. The readback still runs, so the screen
states what the entry holds when the kernel takes over:

    s2cr=00020000  firmware's bypass is in place
    s2cr=00000052  firmware did not reach it, or the write was dropped

usage: prepare-shengufs-smmu-readonly.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "No SMMU store at all"

OLD = """  const char *failure = configureUfsSmmu (plan, stream,
    [smmu](unsigned offset) { return read32 (smmu, offset); },
    [smmu](unsigned offset, uint32_t value) {
      write32 (smmu, offset, value);
      __asm__ volatile ("dsb sy" ::: "memory");
    });"""

NEW = """  // No SMMU store at all: firmware puts this stream in bypass before the OS
  // starts, and any write from here resets the part. The mapping is kept
  // because the fault registers are read from it later.
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
        print(f"  {path}: SMMU left read-only")

    if not patched:
        print("  !! NativeUfs.cpp not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
