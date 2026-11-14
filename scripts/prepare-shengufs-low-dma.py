#!/usr/bin/env python3
"""Ask for a DMA buffer below 4 GiB, whatever CAP.64AS says.

The controller advertises 64-bit addressing (CAP bit 24, 0x01000000, set in
0xd5c7031f), so hostBringUp() allocates the request list and its buffers without
an upper bound and the run lands at 0x9cc5e2000 - above 4 GiB.

The stream's SMMU entry is the one firmware left behind, and the table behind it
was built by the previous OS for its own buffers, which were all below 4 GiB.
Any transaction the controller issues to an address outside that window is
never answered, which is exactly the measured shape: the doorbell reads set, IS
stays clear and no descriptor is ever fetched, with every legacy write reading
back what was written.

The SMMU cannot be reprogrammed from the kernel on this part - a single S2CR
write resets the board - so the cheapest way to test the window is to stay
inside it. This patch asks for a low buffer and leaves the SMMU alone.

usage: prepare-shengufs-low-dma.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "Ask for a low buffer instead"

OLD = "  const bool wide = read32 (gHost.hc, 0) & 0x01000000;"

NEW = """  // The stream map is the identity window the previous OS built, and every
  // buffer it described sat below 4 GiB. Ask for a low buffer instead of
  // trusting CAP.64AS: an address outside that window is never answered, and
  // the controller then never fetches a descriptor at all.
  const bool wide = false;"""


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
            print(f"  !! {path}: wide anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD, NEW, 1))
        patched += 1
        print(f"  {path}: DMA buffers kept below 4 GiB")

    if not patched:
        print("  !! NativeUfs.cpp not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
