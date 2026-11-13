#!/usr/bin/env python3
"""Leave a post-mortem record in RAM before the fatal step.

This board has no serial port, and the reset that ends a run can be too fast for
the panic screen to draw. The one channel that survives is memory: the firmware
keeps its own log at a fixed address, and DRAM is not cleared by a warm reset,
so a record written just before a fatal register write is still there when the
tablet comes back up.

The record lives at a fixed physical page of its own and is dumped by the
firmware on the next boot (`fastboot oem debuglog` / `get_staged`).

Stages:
  1  about to configure the UFS stream in the SMMU
  2  SMMU configuration returned
  3  request list started, first command sent
  4  first command completed or timed out

usage: prepare-shengufs-deathlog.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import pathlib
import re
import sys

HELPER = """// Post-mortem record. Fixed physical page, read back by the UEFI firmware after
// a reset: the panic screen cannot be trusted when the failure is a register
// write that resets the SoC. See prepare-shengufs-deathlog.py.
#define kDeathPhys  0xD7E00000ULL
struct DeathRecord {
  char     magic[8];      // "XNUDEAD1"
  uint32_t stage;
  uint32_t length;
  uint64_t s2cr;
  uint64_t dma;
  char     text[200];
};
static void deathMark (uint32_t stage, const char *text, uint64_t s2cr = 0, uint64_t dma = 0)
{
  static uintptr_t page = 0;
  static OSSharedPtr<IOMemoryMap> keep;
  if (!page) {
    page = mapPhys (kDeathPhys, 4096, keep);
    if (!page) return;
  }
  DeathRecord *record = reinterpret_cast<DeathRecord *> (page);
  size_t length = strlen (text);
  if (length > sizeof (record->text) - 1) length = sizeof (record->text) - 1;
  memset (record, 0, sizeof (*record));
  memcpy (record->magic, "XNUDEAD1", 8);
  record->stage = stage;
  record->length = static_cast<uint32_t> (length);
  record->s2cr = s2cr;
  record->dma = dma;
  memcpy (record->text, text, length);
  __asm__ volatile ("dsb sy" ::: "memory");
  for (uintptr_t line = reinterpret_cast<uintptr_t> (record) & ~uintptr_t (63);
       line < reinterpret_cast<uintptr_t> (record) + sizeof (*record); line += 64) {
    __asm__ volatile ("dc civac, %0" :: "r" (line) : "memory");
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}

"""

ANCHOR = "static void smmuBypassStream (uint16_t stream, OSSharedPtr<IOMemoryMap> &keep, uint32_t *report,\n"

ROOT_CALL = re.compile(r"^(?P<ind>[ \t]*)smmuBypassStream \(0x60, gHost\.smmuMap, report, "
                       r"gHost\.phys, [^)]*\);[ \t]*\r?\n", re.M)

ADOPT_CALL = re.compile(r"^(?P<ind>[ \t]*)smmuBypassStream \(0x60, smmuMap, smmuReport, phys, 16384\);[ \t]*\r?\n", re.M)

QUEUE_START = re.compile(r"^(?P<ind>[ \t]*)if \(!hostStartQueue \(why\)\) return false;[ \t]*\r?\n", re.M)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "deathMark" in text and "kDeathPhys" in text:
            print(f"  {path}: already patched")
            patched += 1
            continue
        if ANCHOR not in text:
            print(f"  !! {path}: smmuBypassStream anchor not found", file=sys.stderr)
            continue

        text = text.replace(ANCHOR, HELPER + ANCHOR, 1)

        # root path: mark before and after the stream configuration
        m = ROOT_CALL.search(text)
        if m:
            ind = m.group("ind")
            before = (f'{ind}deathMark (1, "before smmu bypass", 0, gHost.phys);\n')
            after = (f'{ind}deathMark (2, "after smmu bypass", 0, gHost.phys);\n')
            text = text[:m.start()] + before + text[m.start():m.end()] + after + text[m.end():]
        else:
            print(f"  !! {path}: root bypass call not found", file=sys.stderr)

        # adopt path: same two marks around its call
        m = ADOPT_CALL.search(text)
        if m:
            ind = m.group("ind")
            text = (text[:m.start()] + f'{ind}deathMark (1, "adopt before smmu", 0, phys);\n' +
                    text[m.start():m.end()] + f'{ind}deathMark (2, "adopt after smmu", 0, phys);\n' +
                    text[m.end():])

        # queue start: prove the request list is running before the first command
        m = QUEUE_START.search(text)
        if m:
            ind = m.group("ind")
            text = (text[:m.end()] + f'{ind}deathMark (3, "queue started");\n' + text[m.end():])

        path.write_text(text)
        patched += 1
        print(f"  {path}: death record installed")

    if not patched:
        print("  !! no NativeUfs.cpp patched", file=sys.stderr)
        return 1
    print(f"death log: {patched} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
