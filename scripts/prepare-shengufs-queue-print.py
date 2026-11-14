#!/usr/bin/env python3
"""Print the request-list takeover step by step, in RootQueue.h.

What is left to explain is the step after the takeover succeeds: the doorbell is
set, IS stays clear and the first command never completes. hostStartQueue() is
where the list base is programmed and the run-stop bit is raised, so it is the
place that has to say what the controller did with them.

An earlier attempt cycled HCE at the adopt site instead. It could not work:
hostStopQueue() refuses to touch the controller unless HCE is already set and
HCS reads 0x0f, so that patch stopped the boot before its own prints, and the
build answered with compiler errors rather than a measurement.

Prints via printf(), which reaches console_write_char - the same path panic()
draws with - and execution continues, so one boot reports all four steps:

    Q[1] stop pre     hcs hce is db
    Q[2] stop post    utrlrsr ie hcs
    Q[3] start base   want got hcs
    Q[4] start done   utrlrsr hcs is db ie

usage: prepare-shengufs-queue-print.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "Q[1] stop pre"

STOP_HEAD = """static bool hostStopQueue (const char **why)
{
"""

STOP_PRINT = """  printf ("Q[1] stop pre       hcs=%08x hce=%08x is=%08x db=%08x\\n",
          read32 (gHost.hc, 0x30), read32 (gHost.hc, 0x34),
          read32 (gHost.hc, 0x20), read32 (gHost.hc, 0x58));
"""

STOP_RET_OLD = """  if (!hostWaitRegister (0x60, 1, 0)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list stop";
    return false;
  }
  return true;"""

STOP_RET_NEW = """  if (!hostWaitRegister (0x60, 1, 0)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list stop";
    return false;
  }
  printf ("Q[2] stop post      utrlrsr=%08x ie=%08x hcs=%08x\\n",
          read32 (gHost.hc, 0x60), read32 (gHost.hc, 0x24), read32 (gHost.hc, 0x30));
  return true;"""

START_BASE_OLD = """  if (read32 (gHost.hc, 0x50) != uint32_t (list) ||
      read32 (gHost.hc, 0x54) != uint32_t (list >> 32)) {"""

START_BASE_NEW = """  printf ("Q[3] start base     want=%08x/%08x got=%08x/%08x hcs=%08x\\n",
          static_cast<uint32_t> (list), static_cast<uint32_t> (list >> 32),
          read32 (gHost.hc, 0x50), read32 (gHost.hc, 0x54), read32 (gHost.hc, 0x30));
  if (read32 (gHost.hc, 0x50) != uint32_t (list) ||
      read32 (gHost.hc, 0x54) != uint32_t (list >> 32)) {"""

START_RET_OLD = """  if (!hostWaitRegister (0x60, 1, 1) || !hostWaitRegister (0x30, 3, 3)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list ready";
    return false;
  }
  return true;"""

START_RET_NEW = """  printf ("Q[4] start done     utrlrsr=%08x hcs=%08x is=%08x db=%08x ie=%08x\\n",
          read32 (gHost.hc, 0x60), read32 (gHost.hc, 0x30), read32 (gHost.hc, 0x20),
          read32 (gHost.hc, 0x58), read32 (gHost.hc, 0x24));
  if (!hostWaitRegister (0x60, 1, 1) || !hostWaitRegister (0x30, 3, 3)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list ready";
    return false;
  }
  return true;"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("RootQueue.h"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if MARKER in text:
            print(f"  {path}: already patched")
            patched += 1
            continue
        if STOP_HEAD not in text:
            print(f"  !! {path}: hostStopQueue not found", file=sys.stderr)
            continue
        body = text[text.index(STOP_HEAD) + len(STOP_HEAD):]
        text = text.replace(STOP_HEAD, STOP_HEAD + STOP_PRINT + body[:0], 1)
        for old, new, what in (
            (STOP_RET_OLD, STOP_RET_NEW, "stop return"),
            (START_BASE_OLD, START_BASE_NEW, "start base"),
            (START_RET_OLD, START_RET_NEW, "start return"),
        ):
            if old not in text:
                print(f"  !! {path}: {what} anchor not found", file=sys.stderr)
                return 1
            text = text.replace(old, new, 1)
        path.write_text(text)
        patched += 1
        print(f"  {path}: queue takeover prints its registers")

    if not patched:
        print("  !! RootQueue.h not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
