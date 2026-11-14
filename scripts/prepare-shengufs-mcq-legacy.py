#!/usr/bin/env python3
"""Select legacy SDB mode before programming the legacy queue registers.

piano's Android reports use_mcq_mode=Y and hba->ufs_version=0x400: this is a
UFSHCI 4.0 controller and the driver runs it with Multi-Circular Queues. In MCQ
mode the legacy registers this driver uses are ignored:

    REG_UTP_TRANSFER_REQ_LIST_BASE_L/H   0x50/0x54   not looked at
    REG_UTP_TRANSFER_REQ_DOOR_BELL       0x58        not looked at
    REG_UTP_TRANSFER_REQ_LIST_RUN_STOP   0x60        not looked at

which is exactly the measured shape: the doorbell reads set, IS stays clear and
no descriptor is ever fetched, with every legacy write reading back the value
that was written.

The selector is REG_UFS_MEM_CFG (0x300), bit 0 (MCQ_MODE_SELECT), and it may
only be changed with the controller disabled, so the mode is switched inside an
HCE 1->0->1 cycle. The identification registers are printed on every boot, so a
run states the mode either way: CAP bit 30 is MCQ_SUPPORT and MCQCAP says what
the part can do.

prints:
    UFSID ver cap mcqcap memcfg
    UFSID mcq off memcfg hce
    UFSID legacy hcs hce memcfg

usage: prepare-shengufs-mcq-legacy.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "UFSID mcq off"

HEAD = """static bool hostStopQueue (const char **why)
{
"""

PROBE = """  // A UFSHCI 4.0 part can come up with MCQ selected, and then every legacy
  // queue register below is silently ignored. Read the identification
  // registers on every boot, so the log says which mode the part is in, and
  // switch to legacy SDB with the controller disabled when MCQ is selected.
  printf ("UFSID ver=%08x cap=%08x mcq=%08x memcfg=%08x\\n",
          read32 (gHost.hc, 0x08), read32 (gHost.hc, 0x00),
          read32 (gHost.hc, 0x04), read32 (gHost.hc, 0x300));
  if ((read32 (gHost.hc, 0x300) & 1) != 0) {
    uint32_t memCfg = read32 (gHost.hc, 0x300);
    hostWrite (0x34, 0);
    for (uint32_t spin = 0; spin < 10000; spin++) {
      if ((read32 (gHost.hc, 0x34) & 1) == 0) break;
      IODelay (10);
    }
    hostWrite (0x300, memCfg & ~1U);
    printf ("UFSID mcq off memcfg=%08x hce=%08x\\n",
            read32 (gHost.hc, 0x300), read32 (gHost.hc, 0x34));
    hostWrite (0x34, 1);
    for (uint32_t spin = 0; spin < 200000; spin++) {
      if (read32 (gHost.hc, 0x34) & 1) break;
      IODelay (10);
    }
    printf ("UFSID legacy hcs=%08x hce=%08x memcfg=%08x\\n",
            read32 (gHost.hc, 0x30), read32 (gHost.hc, 0x34),
            read32 (gHost.hc, 0x300));
  }

"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("RootQueue.h"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if MARKER in text:
            print(f"  {path}: already patched")
            patched += 1
            continue
        if HEAD not in text:
            print(f"  !! {path}: hostStopQueue header not found", file=sys.stderr)
            continue
        text = text.replace(HEAD, HEAD + PROBE, 1)
        path.write_text(text)
        patched += 1
        print(f"  {path}: legacy SDB selected when MCQ is active")

    if not patched:
        print("  !! RootQueue.h not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
