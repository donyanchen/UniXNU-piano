#!/usr/bin/env python3
"""Let the UFS root layout live in a window that is not the userdata partition.

The ShengUfs root driver reads LBA 0 of LUN 0, expects a GPT there, and takes
the manifest from the start of the partition named "userdata". That forces the
iPadOS image to overwrite the first blocks of Android's /data, which this board
must not do.

Give the driver a base offset instead: native-ufs-window-lba=N makes every read
add N 4 KiB blocks, so LBA 0 becomes the first block of a window anywhere on the
device. A file written into /data and pinned there can then carry its own GPT and
manifest, and the boot argument points at its first physical block.

SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import sys

OLD_DECL = """static IOReturn hostRead4k (uint8_t lun, uint64_t lba, uint32_t blocks, void *dst)
{"""
NEW_DECL = """// Base of the window the GPT and the root manifest are read from. Zero keeps the
// historical behaviour (LUN 0, absolute blocks); native-ufs-window-lba moves it,
// so a pinned file inside /data can carry the image without touching the
// partition Android lives in.
static uint64_t gWindowBaseLba;
static uint64_t gWindowBlocks;

static IOReturn hostRead4k (uint8_t lun, uint64_t lba, uint32_t blocks, void *dst)
{
  lba += gWindowBaseLba;"""

OLD_START = """  bool probe (IOService *provider, SInt32 *score) override;"""
NEW_START = """  bool probe (IOService *provider, SInt32 *score) override;"""

# Parse the argument where the other UFS arguments are read.
OLD_PARSE = """  PE_parse_boot_argn ("native-ufs-root", &rootMode, sizeof (rootMode));"""
NEW_PARSE = """  PE_parse_boot_argn ("native-ufs-root", &rootMode, sizeof (rootMode));
  {
    uint64_t window = 0, blocks = 0;
    if (PE_parse_boot_argn ("native-ufs-window-lba", &window, sizeof (window)) && window) {
      gWindowBaseLba = window;
    }
    if (PE_parse_boot_argn ("native-ufs-window-blocks", &blocks, sizeof (blocks)) && blocks) {
      gWindowBlocks = blocks;
    }
  }"""


# RootLayout.h: window mode skips the GPT walk and reads the manifest at relative LBA 0.
LAYOUT_OLD = """  gRootDiagnostic.stage = \"GPT header\";"""
LAYOUT_NEW = """  if (gWindowBaseLba && gWindowBlocks) {
    // Window mode: the caller named a block range that starts with the root
    // manifest, so there is no GPT to walk.
    layout->userdataFirst = 0;
    layout->userdataLast = gWindowBlocks - 1;
    layout->gptEntryCount = 0;
    layout->gptEntriesLba = 0;
    goto manifest;
  }
  gRootDiagnostic.stage = \"GPT header\";"""
LAYOUT_LABEL_OLD = """  gRootDiagnostic.first = layout->userdataFirst;"""
LAYOUT_LABEL_NEW = """manifest:
  gRootDiagnostic.first = layout->userdataFirst;"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("RootCommands.h"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "gWindowBaseLba" in text:
            continue
        if OLD_DECL not in text:
            print(f"  !! {path}: hostRead4k not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD_DECL, NEW_DECL, 1))
        patched += 1
        print(f"  {path}: read base offset added")

    parsed = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "native-ufs-window-lba" in text:
            continue
        if OLD_PARSE not in text:
            print(f"  !! {path}: boot argument parse site not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD_PARSE, NEW_PARSE, 1))
        parsed += 1
        print(f"  {path}: native-ufs-window-lba parsed")

    layouts = 0
    for path in pathlib.Path(args.root).rglob("RootLayout.h"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "goto manifest" in text:
            continue
        if LAYOUT_OLD not in text or LAYOUT_LABEL_OLD not in text:
            print(f"  !! {path}: layout anchors not found", file=sys.stderr)
            continue
        text = text.replace(LAYOUT_OLD, LAYOUT_NEW, 1).replace(LAYOUT_LABEL_OLD, LAYOUT_LABEL_NEW, 1)
        path.write_text(text)
        layouts += 1
        print(f"  {path}: window mode added to the layout parser")

    if patched == 0 or parsed == 0 or layouts == 0:
        print("  !! window override not installed", file=sys.stderr)
        return 1
    print(f"ufs window: {patched} reader(s), {parsed} parser(s), {layouts} layout(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
