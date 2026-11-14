#!/usr/bin/env python3
"""Bring the UFS host controller up the way Linux does, instead of adopting it.

Mainline (see the liuqin port) never trusts the loader's controller state: it
stops the controller, programs both request-list bases, starts them, then runs a
UIC link startup and waits for ULSS. ShengUfs instead takes the ABL's state
over, and on this board that state answers nothing - the doorbell stays set, IS
stays clear, and even UIC commands are refused.

Do the Linux sequence before the first command. If the controller still cannot
report UCRDY/UTRLRDY/UTMRDY after that, say so and stop.

usage: prepare-shengufs-hba-reset.py <build tree root>
"""
import argparse
import pathlib
import sys

ANCHOR = """  uint32_t hcsBefore = read32 (hc, 0x30);"""

SOLUTION = """  //
  // Full host-controller bring-up, the way mainline ufshcd does it: stop the
  // controller, program both request-list bases, start them, then start the
  // link. Adopting the loader's state is what left this board unable to answer
  // any command at all.
  //
  {
    uint32_t hcsRaw = read32 (hc, 0x30);
    write32 (hc, 0x34, 0);                       // HCE = 0
    for (unsigned spin = 0; spin < 10000; spin++) {
      if ((read32 (hc, 0x34) & 1) == 0) break;
      IODelay (10);
    }
    write32 (hc, 0x50, static_cast<uint32_t> (phys));
    write32 (hc, 0x54, static_cast<uint32_t> (phys >> 32));
    write32 (hc, 0x70, static_cast<uint32_t> (phys));
    write32 (hc, 0x74, static_cast<uint32_t> (phys >> 32));
    write32 (hc, 0x34, 1);                       // HCE = 1
    for (unsigned spin = 0; spin < 10000; spin++) {
      if (read32 (hc, 0x30) & 1) break;          // UCRDY
      IODelay (10);
    }
    for (unsigned spin = 0; spin < 10000; spin++) {
      if ((read32 (hc, 0x30) & 6) == 6) break;   // UTRLRDY | UTMRDY
      IODelay (10);
    }
    write32 (hc, 0x60, 1);                       // UTRLRSR
    write32 (hc, 0x44, 0);
    write32 (hc, 0x48, 0);
    write32 (hc, 0x4C, 0);
    write32 (hc, 0x40, 0x16);                    // DME_LINKSTARTUP
    for (unsigned spin = 0; spin < 20000; spin++) {
      if (read32 (hc, 0x20) & 4) break;
      IODelay (10);
    }
    write32 (hc, 0x20, 4);
    if ((read32 (hc, 0x30) & 7) != 7) {
      panic ("NATIVE_UFS adopt: hba reset left the controller unusable hcs=%08x->%08x is=%08x debug=%08x",
             hcsRaw, read32 (hc, 0x30), read32 (hc, 0x20), read32 (hc, 0x34));
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
        if "hba reset left the controller unusable" in text:
            continue
        if ANCHOR not in text:
            print(f"  !! {path}: anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(ANCHOR, SOLUTION + ANCHOR, 1))
        patched += 1
        print(f"  {path}: controller brought up the way Linux does")
    if not patched:
        print("  !! hba reset not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
