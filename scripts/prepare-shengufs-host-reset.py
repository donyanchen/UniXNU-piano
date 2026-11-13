#!/usr/bin/env python3
"""Reset the UFS controller and start the link before taking the queue over.

The panic after a successful stage reads:

    hcs=0000010f hce=00000001 is=00000000 db=00000001 rsr=00000001 ocs=0f

The link reports up, the controller is enabled, the request list is running, the
doorbell is still set and IS never changed: the controller never fetched the
command. This board hands the controller over from the ABL with its own request
list and a link state ours never picks up - the vendor UFSDxe needed a link
reset here for exactly the same reason (tools/patch-qcom-dxe.sh).

So cycle HCE, issue UIC DME_LINKSTARTUP ourselves, and only then start the queue
and send the NOP OUT.

usage: prepare-shengufs-host-reset.py <build tree root>
"""
import argparse
import pathlib
import sys

SOLUTION = """  //
  // The ABL leaves the controller ready (HCS low nibble 0x0f) with its own
  // request list, and our first NOP OUT never completes: the doorbell stays set
  // and IS stays clear, so the command is never fetched. Leave HCE and the list
  // base alone - cycling HCE clears UTRLBA and the controller then never reports
  // ready again - and only restart the link through the UIC path.
  //
  write32 (gHost.hc, 0x44, 0);
  write32 (gHost.hc, 0x48, 0);
  write32 (gHost.hc, 0x4C, 0);
  write32 (gHost.hc, 0x40, 0x16);              // DME_LINKSTARTUP
  for (uint32_t spin = 0; spin < 20000; spin++) {
    if (read32 (gHost.hc, 0x20) & 4) break;    // UIC command completion
    IODelay (10);
  }
  write32 (gHost.hc, 0x20, 4);
  gRootDiagnostic.uic[0] = read32 (gHost.hc, 0x30);
  gRootDiagnostic.uic[1] = read32 (gHost.hc, 0x34);
  gRootDiagnostic.uic[2] = read32 (gHost.hc, 0x40);

"""

ANCHOR = "  if (!hostStopQueue (why)) return false;"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "DME_LINKSTARTUP" in text:
            continue
        if ANCHOR not in text:
            print(f"  !! {path}: anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(ANCHOR, SOLUTION + ANCHOR, 1))
        patched += 1
        print(f"  {path}: controller cycled, link started before the queue")

    if not patched:
        print("  !! host reset not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())