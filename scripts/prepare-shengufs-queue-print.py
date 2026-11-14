#!/usr/bin/env python3
"""Print one line per queue-takeover step, from RootQueue.h.

What is left to explain is the step after the takeover succeeds: the doorbell is
set, IS stays clear and the first command never completes. hostStartQueue() is
where the list base is programmed and the run-stop bit is raised, so it is the
place that has to report what the controller did with them.

Two lines only, each emitted at the end of its function, because printf() also
feeds the kernel log buffer: a boot must not be able to flood it.

    UFSQ stop  hcs hce is ie rsr
    UFSQ start utrlrsr hcs is db ie ba lo/hi

Anchors are function-local and never match text another patch may have edited:
the previous rewrite keyed on the request-list address comparison, which
prepare-shengufs-deathlog.py rewrites (it injects a deathMark around the SMMU
call), and the build stopped with "start base anchor not found".

usage: prepare-shengufs-queue-print.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "UFSQ stop"

STOP_FN = """static bool hostStopQueue (const char **why)"""
START_FN = """static bool hostStartQueue (const char **why)"""

STOP_TAIL = """  hostWrite (0x24, 0);
  hostWrite (0x60, 0);
  if (!hostWaitRegister (0x60, 1, 0)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list stop";
    return false;
  }
  return true;"""

STOP_TAIL_NEW = """  hostWrite (0x24, 0);
  hostWrite (0x60, 0);
  if (!hostWaitRegister (0x60, 1, 0)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list stop";
    printf ("UFSQ stop  hcs=%08x hce=%08x is=%08x ie=%08x rsr=%08x FAILED\\n",
            read32 (gHost.hc, 0x30), read32 (gHost.hc, 0x34), read32 (gHost.hc, 0x20),
            read32 (gHost.hc, 0x24), read32 (gHost.hc, 0x60));
    return false;
  }
  printf ("UFSQ stop  hcs=%08x hce=%08x is=%08x ie=%08x rsr=%08x\\n",
          read32 (gHost.hc, 0x30), read32 (gHost.hc, 0x34), read32 (gHost.hc, 0x20),
          read32 (gHost.hc, 0x24), read32 (gHost.hc, 0x60));
  return true;"""

START_TAIL = """  hostWrite (0x60, 1);"""

START_TAIL_NEW = """  hostWrite (0x60, 1);
  printf ("UFSQ start rsr=%08x hcs=%08x is=%08x db=%08x ie=%08x ba=%08x/%08x\\n",
          read32 (gHost.hc, 0x60), read32 (gHost.hc, 0x30), read32 (gHost.hc, 0x20),
          read32 (gHost.hc, 0x58), read32 (gHost.hc, 0x24),
          read32 (gHost.hc, 0x50), read32 (gHost.hc, 0x54));"""


def replace_tail(text, fn_header, old_tail, new_tail, what, path):
    """Replace the tail inside the function whose header is fn_header.

    The old tail is removed from the function body and the new one put in its
    place, so no anchor can straddle a line another patch owns.
    """
    start = text.find(fn_header)
    if start < 0:
        print(f"  !! {path}: {what} function not found", file=sys.stderr)
        return None
    end = text.find("\n}\n", start)
    if end < 0:
        print(f"  !! {path}: {what} function end not found", file=sys.stderr)
        return None
    body = text[start:end]
    if old_tail not in body:
        print(f"  !! {path}: {what} tail not found", file=sys.stderr)
        return None
    return text[:start] + body.replace(old_tail, new_tail.rstrip("\n"), 1) + text[end:]


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
        text = replace_tail(text, STOP_FN, STOP_TAIL, STOP_TAIL_NEW, "hostStopQueue", path)
        if text is None:
            continue
        text = replace_tail(text, START_FN, START_TAIL, START_TAIL_NEW, "hostStartQueue", path)
        if text is None:
            continue
        path.write_text(text)
        patched += 1
        print(f"  {path}: queue takeover prints two lines")

    if not patched:
        print("  !! RootQueue.h not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
