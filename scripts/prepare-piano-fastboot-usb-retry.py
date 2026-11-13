#!/usr/bin/env python3
"""Make the firmware retry the USB device role when the host never connects.

The DWC3 controller routinely reports StartEx success at the ABL handoff and
still never puts the device on the bus: the host sees a Type-C partner but no
USB device, so `fastboot stage` can never happen and the menu runs without a
payload. Nothing in the firmware reacted to that state; the packet poll just
spun for 180 s.

Track the one signal that means the host really enumerated us (a
UsbDeviceStateConnected event) and, while it never arrives, drop and re-run the
device role every five seconds. That is the same thing a cable replug does, and
it is the only lever the firmware has.

usage: prepare-piano-fastboot-usb-retry.py <uefi-checkout>
"""
import argparse
import pathlib
import sys

TARGET = "uefi/pianoPkg/Library/DeviceBootManagerLib/PianoFastboot.c"

GLOBAL_OLD = """STATIC BOOLEAN                mVolumeReady;"""

GLOBAL_NEW = """STATIC BOOLEAN                mVolumeReady;

//
// The DWC3 controller the fastboot stack drives. Its mode bits decide whether
// the port is a device at all, and nothing prints them today: a controller left
// in host mode reports StartEx success and then never appears on the bus.
//
#define DWC3_BASE  0x0A600000UL

STATIC
UINT32
Dwc3Read (
  IN UINT32  Offset
  )
{
  return *(volatile UINT32 *)(UINTN)(DWC3_BASE + Offset);
}

STATIC
VOID
Dwc3Dump (
  IN CONST CHAR16  *Where
  )
{
  Print (L"usb[%s]: dcfg=%08x dctl=%08x devten=%08x dsts=%08x\\n",
         Where, Dwc3Read (0x0000), Dwc3Read (0x0014), Dwc3Read (0x0008), Dwc3Read (0x0034));
  Print (L"usb[%s]: gctl=%08x phy2=%08x pipe3=%08x\\n",
         Where, Dwc3Read (0xC110), Dwc3Read (0xC200), Dwc3Read (0xC2C0));
}

//
// Set when the host completes SET_CONFIGURATION. Never set means the host did
// not enumerate us at all, which is the failure this board hits at the ABL
// handoff, and the only state in which re-running the device role is safe.
//
STATIC BOOLEAN                mHostConnected;"""

CONNECT_OLD = """    if (Payload.DeviceState == UsbDeviceStateConnected) {
      mNext = FbNextCommand;"""

CONNECT_NEW = """    if (Payload.DeviceState == UsbDeviceStateConnected) {
      mHostConnected = TRUE;
      mNext = FbNextCommand;"""

STARTEX_OLD = """    Print (L"fastboot: StartEx %r after %u tries\\n", Status, Tries);
    gBS->Stall (2000000);"""

STARTEX_NEW = """    Print (L"fastboot: StartEx %r after %u tries\\n", Status, Tries);
    if (!EFI_ERROR (Status)) {
      Dwc3Dump (L"after StartEx");
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
    // The host has not enumerated the device: StartEx reported success but the
    // bus never saw us. Drop the device role and run it again, once every five
    // seconds, so the host is presented with a fresh attach - the same thing
    // unplugging and replugging the cable does, which is the only way this
    // board recovers. Skip it entirely once the host has connected: a re-attach
    // in the middle of a staged transfer would throw the transfer away.
    //
    if (!mHostConnected && !mVolumeReady && (Elapsed != 0) && ((Elapsed % 5000) < 10)) {
      Print (L"fastboot: no host after %u ms, re-running the device role\\n", (UINT32)Elapsed);
      Dwc3Dump (L"before retry");
      mUsb->Stop ();
      gBS->Stall (200000);
      mUsb->StartEx (&mDescSet);
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
    if "mHostConnected" in text:
        print(f"  {path}: already patched")
        return 0

    for old, new, what in (
        (GLOBAL_OLD, GLOBAL_NEW, "volume globals"),
        (CONNECT_OLD, CONNECT_NEW, "connected event"),
        (STARTEX_OLD, STARTEX_NEW, "StartEx dump"),
        (LOOP_OLD, LOOP_NEW, "payload wait loop"),
    ):
        if old not in text:
            print(f"  !! {what} anchor not found", file=sys.stderr)
            return 1
        text = text.replace(old, new, 1)

    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    print(f"  {path}: the device role is retried while the host stays away")
    return 0


if __name__ == "__main__":
    sys.exit(main())