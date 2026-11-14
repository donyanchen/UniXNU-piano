#!/usr/bin/env python3
"""Bring the UFS host controller up the way mainline ufshcd does it.

The adopt probe on the device put the real numbers on the screen for the first
time:

    NATIVE_UFS adopt: hba reset left the controller unusable
    hcs=0000010F->00000008  is=00000000  debug=00000001

0x10F is UCRDY|UTRLRDY|UTMRDY|UPMCRS|ULSS. After the write to HCE the status
reads 0x08: UPMCRS alone. CONTROLLER_ENABLE (0x34) reads back 1, so the write
landed and the controller started its own initialisation sequence; the queue
readies are simply not up yet. The previous patch treated "not ready yet" as
"unusable" and stopped there, and it also did the steps in the wrong order:

  * it waited on HCS.UCRDY instead of on CONTROLLER_ENABLE, which is the bit
    the controller raises when its own init sequence completes;
  * it programmed UTRLBA/UTMRBA and set UTRLRSR *before* the link was started,
    while ufshcd_link_startup() runs UIC DME_LINKSTARTUP first and only then
    calls ufshcd_make_hba_operational(), which is what programs the bases,
    enables the interrupts and finally sets the run-stop bits;
  * it never wrote IE (0x24), so IS could only ever read as zero.

This rewrite follows ufshcd.c line for line. Every step records what it read so
that a failure states the step and the registers instead of a guess:

    ufshcd_hba_enable      HCE 1->0->1, wait for CONTROLLER_ENABLE to read back 1
    ufshcd_link_startup    UIC DME_LINKSTARTUP (0x16), wait IS.UCCS, check ULSS
      make_hba_operational enable IE, program UTRLBA/U, UTMRBA/U, read HCS,
                           then UTRLRSR and UTMRRSR
    ufshcd_verify_dev_init NOP OUT sent by the driver afterwards

DME_RESET is not reissued here: ufshcd_probe() runs it before hba_enable, and
the device side of the link is what the old patch's ordering was killing.

usage: prepare-shengufs-hba-reset.py <build tree root>
"""
import argparse
import pathlib
import sys

ANCHOR = """  uint32_t hcsBefore = read32 (hc, 0x30);"""

MARKER = "ufshcd order: hba_enable -> link_startup -> make_hba_operational"

SOLUTION = """  //
  // ufshcd order: hba_enable -> link_startup -> make_hba_operational.
  // ufshcd_probe() does not adopt the loader's state and does not trust it; it
  // replaces it, the way mainline does on every probe.
  //
  {
    uint32_t hcsRaw = read32 (hc, 0x30);
    uint32_t hceRaw;

    // ---- ufshcd_hba_enable: stop, then let the controller init itself ----
    if (read32 (hc, 0x34) & 1) {
      write32 (hc, 0x34, 0);                     // CONTROLLER_ENABLE = 0
      for (unsigned spin = 0; spin < 200000; spin++) {
        if ((read32 (hc, 0x34) & 1) == 0) break;
        IODelay (10);
      }
      if (read32 (hc, 0x34) & 1) {
        panic ("NATIVE_UFS hba: HCE would not clear hce=%08x hcs=%08x",
               read32 (hc, 0x34), read32 (hc, 0x30));
      }
    }

    // The UniPro link is disabled in the controller's own view at this point.
    // Nothing is written for it: mainline only updates hba->uic_link_state.

    write32 (hc, 0x34, 1);                       // CONTROLLER_ENABLE = 1
    for (unsigned spin = 0; spin < 200000; spin++) {
      if (read32 (hc, 0x34) & 1) break;
      IODelay (10);
    }
    hceRaw = read32 (hc, 0x34);
    if ((hceRaw & 1) == 0) {
      panic ("NATIVE_UFS hba: controller never enabled hce=%08x hcs=%08x is=%08x",
             hceRaw, read32 (hc, 0x30), read32 (hc, 0x20));
    }

    // ---- ufshcd_link_startup: UIC DME_LINKSTARTUP, then IS.UCCS ----
    write32 (hc, 0x44, 0);                       // UCMDARG1
    write32 (hc, 0x48, 0);                       // UCMDARG2
    write32 (hc, 0x4C, 0);                       // UCMDARG3
    write32 (hc, 0x40, 0x16);                    // DME_LINKSTARTUP
    for (unsigned spin = 0; spin < 100000; spin++) {
      if (read32 (hc, 0x20) & 4) break;          // IS.UCCS
      IODelay (10);
    }
    {
      uint32_t isLink = read32 (hc, 0x20);
      uint32_t argLink = read32 (hc, 0x48);
      uint32_t hcsLink = read32 (hc, 0x30);
      write32 (hc, 0x20, 4);                     // clear IS.UCCS
      if ((isLink & 4) == 0) {
        panic ("NATIVE_UFS hba: LINKSTARTUP never completed is=%08x arg=%08x hcs=%08x",
               isLink, argLink, hcsLink);
      }
      if ((hcsLink & 0x100) == 0) {
        panic ("NATIVE_UFS hba: link not up after LINKSTARTUP is=%08x arg=%08x hcs=%08x",
               isLink, argLink, hcsLink);
      }
    }

    // ---- ufshcd_make_hba_operational ----
    write32 (hc, 0x24, 0x0000FFFF);              // IE: every interrupt source
    write32 (hc, 0x38, 0);                       // no interrupt aggregation
    write32 (hc, 0x50, static_cast<uint32_t> (phys));
    write32 (hc, 0x54, static_cast<uint32_t> (phys >> 32));
    write32 (hc, 0x70, static_cast<uint32_t> (phys));
    write32 (hc, 0x74, static_cast<uint32_t> (phys >> 32));
    {
      uint32_t baseL = read32 (hc, 0x50);
      uint32_t baseH = read32 (hc, 0x54);
      uint32_t hcsOp = read32 (hc, 0x30);
      if ((baseL != static_cast<uint32_t> (phys)) ||
          (baseH != static_cast<uint32_t> (phys >> 32))) {
        panic ("NATIVE_UFS hba: UTRLBA did not take want=%08x/%08x got=%08x/%08x",
               static_cast<uint32_t> (phys), static_cast<uint32_t> (phys >> 32), baseL, baseH);
      }
      if ((hcsOp & 0x07) != 0) {
        panic ("NATIVE_UFS hba: list registers not ready hcs=%08x base=%08x/%08x is=%08x ie=%08x",
               hcsOp, baseL, baseH, read32 (hc, 0x20), read32 (hc, 0x24));
      }
    }
    write32 (hc, 0x64, 1);                       // UTMRRSR
    write32 (hc, 0x60, 1);                       // UTRLRSR
    if (((read32 (hc, 0x60) & 1) == 0) || ((read32 (hc, 0x64) & 1) == 0)) {
      panic ("NATIVE_UFS hba: run-stop refused utrlrsr=%08x utmrrsr=%08x hcs=%08x",
             read32 (hc, 0x60), read32 (hc, 0x64), read32 (hc, 0x30));
    }
    (void)hcsRaw;
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
        if MARKER in text:
            print(f"  {path}: already patched")
            continue
        if ANCHOR not in text:
            print(f"  !! {path}: anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(ANCHOR, SOLUTION + ANCHOR, 1))
        patched += 1
        print(f"  {path}: controller brought up in ufshcd order")
    if not patched:
        print("  !! hba reset not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
