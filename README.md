# UniXNU for the Xiaomi Pad 8 Pro (piano)

| | |
| --- | --- |
| What | [UniXNU](https://github.com/UniXNU/UniXNU) device repository: runs iPadOS on the Pad 8 Pro (SM8750) |
| Goes | Next to a `UniXNU` checkout, as `-D ../android_device_xiaomi_piano-unixnu` |
| Comes from | The UniXNU device template, with the SM8750 support of the OnePlus 13T port ([UniXNU-sm8750-common](https://github.com/IssacL04/UniXNU-sm8750-common)) |
| Firmware | A Mu-Silicium based UEFI build; run its `tools/setup-deps.sh`, then build with `--uefi` pointing at its `deps/Mu-Silicium` (see `[firmware]` in `board.toml`) |
| OS | iPadOS 17.7.11 (21H461) |

## State

Experimental, not booted yet. The first goal is XNU's verbose boot log on
the screen from a RAM boot: `fastboot boot` only, nothing is flashed and
Android stays as it was.

## Build

Needs macOS with Xcode. From the UniXNU checkout:

```sh
./unixnu defconfig piano_defconfig -D ../android_device_xiaomi_piano-unixnu
./unixnu fetch
./unixnu build kernel
./unixnu build package
./unixnu build firmware --uefi ../uefi/deps/Mu-Silicium
./unixnu build payload
./unixnu bootimg
fastboot boot <output>/boot/boot.img
```

See [Build and boot](https://unixnu.com/building).
