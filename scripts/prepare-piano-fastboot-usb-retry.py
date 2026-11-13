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