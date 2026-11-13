#!/usr/bin/env python3
"""Run the DWC3 device controller even though the driver never does.

usb[after StartEx] on the board shows gctl in device mode, devten programmed,
and dctl=0x2000 - DCTL.RUN_STOP clear. The controller is therefore stopped and
never answers the host, whatever StartEx reported. Qualcomm's UsbDeviceDxe
waits for a VBUS/charger notification that this board never delivers (PmicDxe is
not loaded: SPMI channel 690 is owned by the ABL), so set the bit ourselves and
keep setting it after every device-role restart.

usage: prepare-piano-fastboot-usb-run.py <uefi-checkout>
"""
import argparse
import pathlib
import sys

TARGET = "uefi/pianoPkg/Library/DeviceBootManagerLib/PianoFastboot.c"

DUMP_OLD = """  Print (L"usb[%s]: gctl=%08x phy2=%08x pipe3=%08x\\n",
         Where, Dwc3Read (0xC110), Dwc3Read (0xC200), Dwc3Read (0xC2C0));
}"""

DUMP_NEW = """  Print (L"usb[%s]: gctl=%08x phy2=%08x pipe3=%08x\\n",
         Where, Dwc3Read (0xC110), Dwc3Read (0xC200), Dwc3Read (0xC2C0));
}

//
// DCTL.RUN_STOP is bit 0. StartEx leaves it clear on this board - the driver
// waits for a charger/VBUS notification that never arrives - and a stopped
// controller never answers the host, no matter that it is in device mode with
// its event buffer armed. Set it and report whether it stuck.
//
STATIC
VOID
Dwc3Run (
  IN CONST CHAR16  *Where
  )
{
  UINT32  Dctl;

  Dctl = Dwc3Read (0x0014);
  if ((Dctl & 1) == 0) {
    *(volatile UINT32 *)(UINTN)(DWC3_BASE + 0x0014) = Dctl | 1;
    gBS->Stall (10000);
  }
  Print (L"usb[%s]: run dctl=%08x dsts=%08x dcfg=%08x\\n",
         Where, Dwc3Read (0x0014), Dwc3Read (0x0034), Dwc3Read (0x0000));
}"""

STARTEX_DUMP_OLD = """    if (!EFI_ERROR (Status)) {
      Dwc3Dump (L"after StartEx");
    }"""

STARTEX_DUMP_NEW = """    if (!EFI_ERROR (Status)) {
      Dwc3Dump (L"after StartEx");
      Dwc3Run (L"after StartEx");
    }"""

RETRY_OLD = """      mUsb->Stop ();
      gBS->Stall (200000);
      mUsb->StartEx (&mDescSet);"""

RETRY_NEW = """      mUsb->Stop ();
      gBS->Stall (200000);
      mUsb->StartEx (&mDescSet);
      Dwc3Run (L"after restart");"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="checkout of the uefi repository")
    args = parser.parse_args()

    path = pathlib.Path(args.root) / TARGET
    if not path.exists():
        print(f"!! {path}: not found", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if "Dwc3Run" in text:
        print(f"  {path}: already patched")
        return 0

    for old, new, what in (
        (DUMP_OLD, DUMP_NEW, "dump helper"),
        (STARTEX_DUMP_OLD, STARTEX_DUMP_NEW, "StartEx site"),
        (RETRY_OLD, RETRY_NEW, "retry site"),
    ):
        if old not in text:
            print(f"  !! {what} anchor not found", file=sys.stderr)
            return 1
        text = text.replace(old, new, 1)

    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    print(f"  {path}: DCTL.RUN_STOP is set after every device-role start")
    return 0


if __name__ == "__main__":
    sys.exit(main())