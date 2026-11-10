#!/usr/bin/env python3
"""Add a console diagnostic to UniXNU's "no boot entry found" fallback.

piano has no serial console, so when the board cannot find its payload the only
evidence is the red line at the bottom of the menu. This rewrites that line so
it says whether the payload volume is reachable at all:

  "no boot entry: payload volume missing"  the volume never got published
  "no boot entry: config unreadable"       the volume is there, the file reads fail

The second case points at the FAT driver or the TOML parser; the first points at
SEC handing the device tree over and UniXNURamDiskDxe publishing the initrd.

Applied by the packaging workflow to the pinned UniXNU checkout. Idempotent.

Usage: apply-unixnu-diagnostics.py <path to UniXNULib/Config.c>
"""
import sys
from pathlib import Path

OLD = '      AsciiStrCpyS (Config->Notice, sizeof (Config->Notice), "no boot entry found");\n'

NEW = r'''      //
      // Board bring-up aid: piano has no serial console, so report on screen
      // whether the payload volume is reachable at all.
      //
      {
        EFI_HANDLE  *DbgVolumes;
        UINTN        DbgCount;
        UINTN        DbgIndex;
        BOOLEAN      DbgConfig;

        DbgVolumes = NULL;
        DbgCount   = 0;
        DbgConfig  = FALSE;
        if (!EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &DbgCount, &DbgVolumes))) {
          for (DbgIndex = 0; DbgIndex < DbgCount; DbgIndex++) {
            if (UniXNUFileExists (DbgVolumes[DbgIndex], L"\\EFI\\UniXNU\\unixnu.toml")) {
              DbgConfig = TRUE;
              break;
            }
          }

          FreePool (DbgVolumes);
        }

        AsciiStrCpyS (
          Config->Notice, sizeof (Config->Notice),
          DbgConfig ? "no boot entry: config unreadable" : "no boot entry: payload volume missing"
          );
      }
'''


def main():
    path = Path(sys.argv[1])
    text = path.read_text()
    if 'payload volume missing' in text:
        print(f'{path}: already patched')
        return
    if OLD not in text:
        sys.exit(f'{path}: anchor not found')
    path.write_text(text.replace(OLD, NEW, 1))
    print(f'{path}: diagnostic added')


if __name__ == '__main__':
    main()
