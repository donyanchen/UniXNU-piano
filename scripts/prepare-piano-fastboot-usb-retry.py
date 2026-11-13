#!/usr/bin/env python3
"""Put the DWC3 device registers where they actually are, and retry quietly.

DWC3 keeps its device block at 0xC700: DCFG 0xC700, DCTL 0xC704, DEVTEN 0xC708,
DSTS 0xC70C. The first version of this patch read 0x0000/0x0014/0x0008/0x0034,
which are global registers, so "DCTL never changes" was a measurement of the
wrong address.

This also drops the Stop ()/StartEx () loop: restarting the device role thirty
times made the vendor driver crash the firmware (black screen, reboot) after the
payload window. The only write it does now is DCTL.RUN_STOP, straight to MMIO.

usage: prepare-piano-fastboot-usb-retry.py <uefi-checkout>
"""
import argparse
import pathlib
import sys

TARGET = "uefi/pianoPkg/Library/DeviceBootManagerLib/PianoFastboot.c"

GLOBAL_OLD = """STATIC BOOLEAN                mVolumeReady;"""

GLOBAL_NEW = """STATIC BOOLEAN                mVolumeReady;

//
// Set when the host completes SET_CONFIGURATION; never set means the host did
// not enumerate us at all.
//
STATIC BOOLEAN                mHostConnected;

//
// DWC3 controller the fastboot stack drives. Device registers live at 0xC700:
// DCFG, DCTL, DEVTEN, DSTS. A controller left with DCTL.RUN_STOP clear never
// answers the host, and nothing prints that today.
//
#define DWC3_BASE   0x0A600000UL
#define DWC3_DCFG   0xC700
#define DWC3_DCTL   0xC704
#define DWC3_DEVTEN 0xC708
#define DWC3_DSTS   0xC70C

STATIC
UINT32
Dwc3Read (
  IN UINT32  Offset
  )
{
  return *(volatile UINT32 *)(UINTN)(DWC3_BASE + Offset);
}

//
// DCTL.RUN_STOP is bit 0. Qualcomm's UsbDeviceDxe never sets it on this board -
// it waits for a charger/VBUS notification that PmicDxe would send, and PmicDxe
// is not loaded - so the firmware believes it started while the controller sits
// stopped. Set it from here; a plain MMIO write cannot disturb the driver.
//
STATIC
VOID
Dwc3Run (
  IN CONST CHAR16  *Where
  )
{
  UINT32  Dctl;

  Dctl = Dwc3Read (DWC3_DCTL);
  if ((Dctl & 1) == 0) {
    *(volatile UINT32 *)(UINTN)(DWC3_BASE + DWC3_DCTL) = Dctl | 1;
    gBS->Stall (10000);
  }

  Print (L"usb[%s]: dctl=%08x dsts=%08x dcfg=%08x devten=%08x\\n",
         Where, Dwc3Read (DWC3_DCTL), Dwc3Read (DWC3_DSTS),
         Dwc3Read (DWC3_DCFG), Dwc3Read (DWC3_DEVTEN));
}

STATIC
VOID
Dwc3Dump (
  IN CONST CHAR16  *Where
  )
{
  Print (L"usb[%s]: gctl=%08x phy2=%08x pipe3=%08x\\n",
         Where, Dwc3Read (0xC110), Dwc3Read (0xC200), Dwc3Read (0xC2C0));
}

//"""

CONNECT_OLD = """    if (Payload.DeviceState == UsbDeviceStateConnected) {
      mNext = FbNextCommand;"""

CONNECT_NEW = """    if (Payload.DeviceState == UsbDeviceStateConnected) {
      mHostConnected = TRUE;
      mNext = FbNextCommand;"""

GLOBAL_HDR_OLD = """STATIC BOOLEAN                mVolumeReady;"""

STARTEX_OLD = """    Print (L"fastboot: StartEx %r after %u tries\\n", Status, Tries);
    gBS->Stall (2000000);"""

STARTEX_NEW = """    Print (L"fastboot: StartEx %r after %u tries\\n", Status, Tries);
    if (!EFI_ERROR (Status)) {
      Dwc3Dump (L"after StartEx");
      Dwc3Run (L"after StartEx");
    }
    gBS->Stall (2000000);"""

LOOP_OLD = """  for (Elapsed = 0; (Elapsed < TimeoutMs) && !mVolumeReady; Elapsed += 10) {
    for (Pumps = 0; (Pumps < 5) && !mVolumeReady; Pumps++) {
      FbPoll (NULL, NULL);
      if (!mVolumeReady) {
        gBS->Stall (2000);
      }
    }
  }"""

LOOP_NEW = """  for (Elapsed = 0; (Elapsed < TimeoutMs) && !mVolumeReady; Elapsed += 10) {
    for (Pumps = 0; (Pumps < 5) && !mVolumeReady; Pumps++) {
      FbPoll (NULL, NULL);
      if (!mVolumeReady) {
        gBS->Stall (2000);
      }
    }

    //
    // Re-assert DCTL.RUN_STOP once every five seconds while the host stays
    // away. MMIO only: the vendor driver's own Stop ()/StartEx () cycle was
    // what crashed the firmware here, not the register.
    //
    if (!mHostConnected && !mVolumeReady && (Elapsed != 0) && ((Elapsed % 5000) < 10)) {
      Dwc3Run (L"retry");
    }
  }"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="checkout of the uefi repository")
    args = parser.parse_args()

    path = pathlib.Path(args.root) / TARGET
    if not path.exists():
        print(f"!! {path}: not found", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if "Dwc3Read" in text:
        print(f"  {path}: already patched")
        return 0

    for old, new, what in (
        (GLOBAL_OLD, GLOBAL_NEW, "volume globals"),
        (CONNECT_OLD, CONNECT_NEW, "connected event"),
        (STARTEX_OLD, STARTEX_NEW, "StartEx site"),
        (LOOP_OLD, LOOP_NEW, "payload wait loop"),
    ):
        if old not in text:
            print(f"  !! {what} anchor not found", file=sys.stderr)
            return 1
        text = text.replace(old, new, 1)

    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    print(f"  {path}: device registers at 0xC700, RUN_STOP re-asserted quietly")
    return 0


if __name__ == "__main__":
    sys.exit(main())