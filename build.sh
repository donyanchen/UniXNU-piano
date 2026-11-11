#!/usr/bin/env bash
set -uo pipefail
cd ../UniXNU
JOBS=${1:-4}
cat > unixnu.local.toml <<CFG
[build]
device = "../device"
jobs = $JOBS
target = "DEBUG"
CFG
run(){ N=$1; shift; echo "### STEP $N"; "$@" > /tmp/$N.log 2>&1 || { echo "::error title=FAILED::$N"; tail -40 /tmp/$N.log | sed 's/^/::error::/'; exit 1; }; tail -6 /tmp/$N.log; }
run defconfig ./unixnu defconfig piano_defconfig -D ../device
run fetch ./unixnu fetch
run ipsw ./unixnu ipsw fetch -D ../device
run tree ./unixnu tree -D ../device
run kernel ./unixnu build kernel -D ../device -j $JOBS
run package ./unixnu build package -D ../device
run firmware ./unixnu build firmware -D ../device --uefi ../uefi/deps/Mu-Silicium
run payload ./unixnu build payload -D ../device
run bootimg ./unixnu bootimg -D ../device --uefi ../uefi/deps/Mu-Silicium --dtb out/piano/ipados-17.7.11-21H461/piano/device-tree/hardware.dtb --ramdisk none
mkdir -p ../out
find out/piano -type f \( -name '*.img' -o -name 'kernel.macho*' -o -name '*.efi' \) -exec cp -v {} ../out/ \; || true
tar czf ../out/logs.tar.gz out/piano/*/*/logs 2>/dev/null || true
cat /tmp/*.log > ../out/build.log 2>/dev/null || true
ls -l ../out
