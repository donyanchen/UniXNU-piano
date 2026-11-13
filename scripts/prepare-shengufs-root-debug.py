#!/usr/bin/env python3
"""Make the ShengUfs root path say why it gave up, in words, on the panic screen.

The driver currently returns false from start() and lets BSD print the generic
"Failed to mount root device 0x... (0x...)", which carries no stage and no
manifest fact. This rewrite turns each root failure into a panic that names the
stage, the window argument the kernel saw, and the first block it read.
"""
import argparse
import pathlib
import sys

OLD_BRINGUP = """  if (!hostBringUp (&why)) {
    rootDiagnosticFailure (why);
    IOLog ("NativeUfs: root bring-up failed: %s\\n", why);
    return false;
  }"""
NEW_BRINGUP = """  if (!hostBringUp (&why)) {
    rootDiagnosticFailure (why);
    panic ("NATIVE_UFS root: bring-up failed: %s", why);
  }"""

OLD_LAYOUT = """  if (!layout || !findRootLayout (layout, &why)) {
    rootDiagnosticFailure (layout ? why : "root layout allocation failed");
    IOLog ("NativeUfs: root layout failed: %s\\n", why);
    if (layout) IOFree (layout, sizeof (RootLayout));
    return false;
  }"""
NEW_LAYOUT = """  if (!layout || !findRootLayout (layout, &why)) {
    rootDiagnosticFailure (layout ? why : "root layout allocation failed");
    panic ("NATIVE_UFS root: layout failed: %s\\n"
           "window base=%llu blocks=%llu",
           layout ? why : "allocation failed", gWindowBaseLba, gWindowBlocks);
  }"""

OLD_MANIFEST = """  if (layout->manifestStatus != 0) {
    rootDiagnosticFailure ("root manifest rejected");
    IOLog ("NativeUfs: no valid root manifest in userdata (status %u, magic %08x %08x)\\n",
           layout->manifestStatus, layout->magic0, layout->magic1);
    IOFree (layout, sizeof (RootLayout));
    return false;
  }"""
NEW_MANIFEST = """  if (layout->manifestStatus != 0) {
    rootDiagnosticFailure ("root manifest rejected");
    panic ("NATIVE_UFS root: manifest status=%u magic=%08x %08x\\n"
           "window base=%llu blocks=%llu first=%llx last=%llx",
           layout->manifestStatus, layout->magic0, layout->magic1,
           gWindowBaseLba, gWindowBlocks, layout->userdataFirst, layout->userdataLast);
  }"""

EDITS = [
    (OLD_BRINGUP, NEW_BRINGUP),
    (OLD_LAYOUT, NEW_LAYOUT),
    (OLD_MANIFEST, NEW_MANIFEST),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args()
    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "NATIVE_UFS root: layout failed" in text:
            continue
        changed = 0
        for old, new in EDITS:
            if old in text:
                text = text.replace(old, new, 1)
                changed += 1
        if changed:
            path.write_text(text)
            patched += 1
            print(f"  {path}: {changed} failure path(s) now print the reason")
    if not patched:
        print("  !! root diagnostics not installed", file=sys.stderr)
        return 1
    print(f"root diagnostics: {patched} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
