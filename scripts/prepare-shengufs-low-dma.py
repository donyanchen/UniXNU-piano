#!/usr/bin/env python3
"""Ask for the DMA buffer below 4 GiB, whatever CAP.64AS says.

hostBringUp() allocates with inTaskWithOptions() and only validates the result
afterwards, so on a controller that advertises 64-bit addressing (CAP bit 24 is
set in 0xd5c7031f) the request list lands at 0x9cc5e2000, above 4 GiB.

The stream's SMMU entry is the one firmware leaves behind, built by the previous
OS for its own buffers, and every one of those sat below 4 GiB. A transaction to
an address outside that window is never answered, which is exactly the measured
shape: the doorbell reads set, IS stays clear, no descriptor is ever fetched,
and every legacy write reads back what was written.

The SMMU cannot be reprogrammed from the kernel here - a single S2CR write
resets the board - so stay inside the window instead. inTaskWithPhysicalMask
asks the allocator for memory whose physical address fits the mask. The call
takes four arguments: inTask, options, capacity, physicalMask. Alignment is not
a parameter - passing one is a compile error, and because the component failure
stops the archive list, the symptom shows up much later as
"_native_verified_root_probe, referenced from _bsd_init".

usage: prepare-shengufs-low-dma.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "inTaskWithPhysicalMask"

OLD = """  gHost.dma = IOBufferMemoryDescriptor::inTaskWithOptions (
    kernel_task, static_cast<IOOptionBits> (kIODirectionInOut) | static_cast<IOOptionBits> (kIOMemoryPhysicallyContiguous) |
    static_cast<IOOptionBits> (kIOMemoryMapperNone),
    kDmaBytes, 4096);"""

NEW = """  // The stream map is the identity window the previous OS built, and every
  // buffer it described sat below 4 GiB. Ask for a low buffer instead of
  // trusting CAP.64AS: an address outside that window is never answered, and
  // the controller then never fetches a descriptor at all. The SMMU itself
  // cannot be touched from here - one S2CR write resets this part.
  gHost.dma = IOBufferMemoryDescriptor::inTaskWithPhysicalMask (
    kernel_task, static_cast<IOOptionBits> (kIODirectionInOut) | static_cast<IOOptionBits> (kIOMemoryPhysicallyContiguous) |
    static_cast<IOOptionBits> (kIOMemoryMapperNone),
    kDmaBytes, 0xFFFFF000ULL);"""


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
            print(f"  !! {path}: DMA allocation anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD, NEW, 1))
        patched += 1
        print(f"  {path}: DMA buffer requested below 4 GiB")

    if not patched:
        print("  !! NativeUfs.cpp not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
