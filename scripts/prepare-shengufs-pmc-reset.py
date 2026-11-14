#!/usr/bin/env python3
"""Clear a pending device power mode change before the first command.

The adopt probe showed the command is never fetched even from the firmware's own
request list:

    adopt: TEST UNIT READY lun0  ocs=f resp=ff scsi=ff
    hcs=0000010F->0000010F is=00000000 db=00000001 rsr=00000001

HCS bit 3 is UPMCRS: a power mode change is pending, and the UTP does not
process commands while it is. Nothing in the driver ever handles it. Issue
DME_RESET (which drops the device's pending UIC/UTP state) and restart the link,
then say whether UPMCRS cleared.

usage: prepare-shengufs-pmc-reset.py <build tree root>
"""
import argparse
import pathlib
import sys

ANCHOR = """  uint32_t hcsBefore = read32 (hc, 0x30);"""

SOLUTION = """  //
  // HCS bit 3 (UPMCRS) is set while the device has a power mode change pending,
  // and the UTP does not process commands until the host completes it. That is
  // exactly the "doorbell set, IS clear, ocs=0xf" shape. Clear it through the
  // device's UIC layer before the queue is touched.
  //
  {
    uint32_t hcsRaw = read32 (hc, 0x30);
    if (hcsRaw & 8) {
      write32 (hc, 0x44, 0);
      write32 (hc, 0x48, 0);
      write32 (hc, 0x4C, 0);
      write32 (hc, 0x40, 0x14);                // DME_RESET
      for (unsigned spin = 0; spin < 20000; spin++) {
        if (read32 (hc, 0x20) & 4) break;
        IODelay (10);
      }
      write32 (hc, 0x20, 4);
      write32 (hc, 0x44, 0);
      write32 (hc, 0x48, 0);
      write32 (hc, 0x4C, 0);
      write32 (hc, 0x40, 0x16);                // DME_LINKSTARTUP
      for (unsigned spin = 0; spin < 20000; spin++) {
        if (read32 (hc, 0x20) & 4) break;
        IODelay (10);
      }
      write32 (hc, 0x20, 4);
      if (read32 (hc, 0x30) & 8) {
        panic ("NATIVE_UFS adopt: PMC survives DME_RESET hcs=%08x->%08x is=%08x",
               hcsRaw, read32 (hc, 0x30), read32 (hc, 0x20));
      }
    }
  }

"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args()
    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "PMC survives DME_RESET" in text:
            continue
        if ANCHOR not in text:
            print(f"  !! {path}: anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(ANCHOR, SOLUTION + ANCHOR, 1))
        patched += 1
        print(f"  {path}: pending PMC cleared before the first command")
    if not patched:
        print("  !! pmc reset not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
