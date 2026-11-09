#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p package scripts
curl -sL -o package/PaganiPeripherals.h https://raw.githubusercontent.com/IssacL04/UniXNU-Pagani_SM8750/main/package/PaganiPeripherals.h
wc -c package/PaganiPeripherals.h
find modules -name 'build-*.py' -exec cp -v {} scripts/ \; 2>/dev/null || true
python3 - <<'PY'
p='board.toml'
s=open(p).read()
if '[package]' not in s:
    open(p,'w').write(s+'\n[package]\nunixnu = "../UniXNU"\n')
print(open(p).read()[-80:])
PY
ls -l package scripts | head
