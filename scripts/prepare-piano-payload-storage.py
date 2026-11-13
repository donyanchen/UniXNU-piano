#!/usr/bin/env python3
"""Let the firmware take the payload from storage when USB never delivers it.

The payload is a 160 MiB FAT volume the firmware publishes as a block device.
Until now it could only arrive over fastboot: `stage payload.img` then
`oem ramdisk`. On this board the DWC3 controller frequently fails to bring the
USB device up at the ABL handoff, so the menu runs with no payload and nothing
can be booted. The host now writes payload.img into the tail of the ipados
partition instead, and this rewrite serves it from there: the volume forwards
reads to the partition's own BlockIo, so the bytes never pass through a 160 MiB
allocation.

usage: prepare-piano-payload-storage.py <uefi-checkout>
"""
import argparse
import pathlib
import sys

TARGET = "uefi/pianoPkg/Library/DeviceBootManagerLib/PianoFastboot.c"

GLOBALS_OLD = """STATIC UINT8                  *mVolumeBase;
STATIC UINTN                  mVolumeBytes;"""

GLOBALS_NEW = """STATIC UINT8                  *mVolumeBase;
STATIC UINTN                  mVolumeBytes;

//
// When the payload lives on storage instead of in a staged transfer buffer, the
// volume is served straight from that partition, so nothing is copied to RAM.
//
STATIC EFI_BLOCK_IO_PROTOCOL  *mVolumeDisk;
STATIC EFI_LBA                 mVolumeDiskLba;
STATIC EFI_LBA                 mVolumeDiskBlocks;

//
// payload.img is written at this offset inside the "ipados" partition: 12 GiB,
// past the 9.4 GiB root image, and 160 MiB long as the builder pads it.
//
#define PAYLOAD_STORAGE_NAME   L"ipados"
#define PAYLOAD_STORAGE_SKIP   (12ULL * 1024 * 1024 * 1024)
#define PAYLOAD_STORAGE_BYTES  (160ULL * 1024 * 1024)

//
// Find the "ipados" partition by walking the GPT of every whole disk and point
// the payload volume at PAYLOAD_STORAGE_SKIP inside it. Returns EFI_SUCCESS
// when mVolumeDisk describes a complete payload.
//
STATIC
EFI_STATUS
PayloadFromDisk (
  VOID
  )
{
  EFI_STATUS              Status;
  EFI_HANDLE             *Handles;
  UINTN                   Count;
  UINTN                   Index;
  UINTN                   Entry;
  EFI_BLOCK_IO_PROTOCOL  *Io;
  UINT8                  *Block;
  UINT8                  *Entries;
  UINT64                  EntriesLba;
  UINT32                  EntryCount;
  UINT32                  EntrySize;
  CHAR16                 *Name;
  UINTN                   Chars;

  Handles = NULL;
  Count   = 0;
  Status  = gBS->LocateHandleBuffer (ByProtocol, &gEfiBlockIoProtocolGuid, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = EFI_NOT_FOUND;

  for (Index = 0; Index < Count; Index++) {
    Io = NULL;
    if (EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiBlockIoProtocolGuid, (VOID **)&Io)) ||
        (Io == NULL) || (Io->Media == NULL) || !Io->Media->MediaPresent || Io->Media->LogicalPartition ||
        (Io->Media->BlockSize < 128)) {
      continue;
    }

    Block = AllocatePool (Io->Media->BlockSize);
    if (Block == NULL) {
      continue;
    }
    if (EFI_ERROR (Io->ReadBlocks (Io, Io->Media->MediaId, 1, Io->Media->BlockSize, Block)) ||
        (CompareMem (Block, "EFI PART", 8) != 0)) {
      FreePool (Block);
      continue;
    }
    EntriesLba = *(UINT64 *)(Block + 72);
    EntryCount = *(UINT32 *)(Block + 80);
    EntrySize  = *(UINT32 *)(Block + 84);
    FreePool (Block);
    if ((EntrySize < 128) || (EntryCount == 0) || (EntryCount > 1024)) {
      continue;
    }

    Entries = AllocatePool ((UINTN)EntrySize * EntryCount);
    if (Entries == NULL) {
      continue;
    }
    if (EFI_ERROR (Io->ReadBlocks (Io, Io->Media->MediaId, EntriesLba, (UINTN)EntrySize * EntryCount, Entries))) {
      FreePool (Entries);
      continue;
    }

    for (Entry = 0; Entry < EntryCount; Entry++) {
      UINT64  FirstLba;
      UINT64  LastLba;
      UINT64  Blocks;

      Name = (CHAR16 *)(Entries + (UINTN)Entry * EntrySize + 56);
      if (Name[0] == 0) {
        continue;
      }
      // A GPT entry name is a 36-character UTF-16 field, not NUL-terminated when full.
      Chars = 0;
      while ((PAYLOAD_STORAGE_NAME[Chars] != 0) && (Chars < 36) && (Name[Chars] == PAYLOAD_STORAGE_NAME[Chars])) {
        Chars++;
      }
      if ((PAYLOAD_STORAGE_NAME[Chars] != 0) || ((Chars < 36) && (Name[Chars] != 0))) {
        continue;
      }

      FirstLba = *(UINT64 *)(Entries + (UINTN)Entry * EntrySize + 32);
      LastLba  = *(UINT64 *)(Entries + (UINTN)Entry * EntrySize + 40);
      Blocks   = PAYLOAD_STORAGE_BYTES / Io->Media->BlockSize;
      if ((Blocks == 0) ||
          (FirstLba + PAYLOAD_STORAGE_SKIP / Io->Media->BlockSize + Blocks - 1 > LastLba)) {
        continue;
      }

      mVolumeDisk       = Io;
      mVolumeDiskLba    = FirstLba + PAYLOAD_STORAGE_SKIP / Io->Media->BlockSize;
      mVolumeDiskBlocks = Blocks;
      FreePool (Entries);
      FreePool (Handles);
      Print (L"fastboot: payload found on storage\\n");
      return EFI_SUCCESS;
    }

    FreePool (Entries);
  }

  FreePool (Handles);
  return Status;
}
"""

VOLREAD_OLD = """  Available = (UINTN)(mVolumeMedia.LastBlock + 1 - Lba) * RAM_BLOCK_SIZE;
  if (BufferSize > Available) {
    CopyMem (Buffer, mVolumeBase + Lba * RAM_BLOCK_SIZE, Available);
    ZeroMem ((UINT8 *)Buffer + Available, BufferSize - Available);
    return EFI_SUCCESS;
  }

  CopyMem (Buffer, mVolumeBase + Lba * RAM_BLOCK_SIZE, BufferSize);
  return EFI_SUCCESS;"""

VOLREAD_NEW = """  Available = (UINTN)(mVolumeMedia.LastBlock + 1 - Lba) * mVolumeMedia.BlockSize;
  if (mVolumeDisk != NULL) {
    UINTN  Read;

    //
    // Forward to the partition that holds the payload. A short tail read is
    // clamped and the rest zeroed, exactly as the staged-buffer path does.
    //
    Read = (BufferSize > Available) ? Available : BufferSize;
    if (EFI_ERROR (mVolumeDisk->ReadBlocks (mVolumeDisk, mVolumeDisk->Media->MediaId,
                                            mVolumeDiskLba + Lba, Read, Buffer))) {
      return EFI_DEVICE_ERROR;
    }
    if (BufferSize > Read) {
      ZeroMem ((UINT8 *)Buffer + Read, BufferSize - Read);
    }
    return EFI_SUCCESS;
  }

  if (BufferSize > Available) {
    CopyMem (Buffer, mVolumeBase + Lba * mVolumeMedia.BlockSize, Available);
    ZeroMem ((UINT8 *)Buffer + Available, BufferSize - Available);
    return EFI_SUCCESS;
  }

  CopyMem (Buffer, mVolumeBase + Lba * mVolumeMedia.BlockSize, BufferSize);
  return EFI_SUCCESS;"""

PUBLISH_ANCHOR = """STATIC
EFI_STATUS
PublishVolume (
  VOID
  )
{"""

CHECK_OLD = """  if ((mData == NULL) || (mDataSize < RAM_BLOCK_SIZE)) {
    return EFI_NOT_FOUND;
  }"""

CHECK_NEW = """  if ((mVolumeDisk == NULL) && ((mData == NULL) || (mDataSize < RAM_BLOCK_SIZE))) {
    return EFI_NOT_FOUND;
  }"""

BASE_OLD = """  mVolumeBase  = (UINT8 *)mData;
  mVolumeBytes = mDataSize;"""

BASE_NEW = """  if (mVolumeDisk != NULL) {
    mVolumeBase  = NULL;
    mVolumeBytes = (UINTN)mVolumeDiskBlocks * mVolumeDisk->Media->BlockSize;
  } else {
    mVolumeBase  = (UINT8 *)mData;
    mVolumeBytes = mDataSize;
  }"""

GEOM_OLD = """  mVolumeMedia.BlockSize        = RAM_BLOCK_SIZE;
  mVolumeMedia.IoAlign          = 1;"""

GEOM_NEW = """  mVolumeMedia.BlockSize        = (mVolumeDisk != NULL) ? mVolumeDisk->Media->BlockSize : RAM_BLOCK_SIZE;
  mVolumeMedia.IoAlign          = (mVolumeDisk != NULL) ? mVolumeDisk->Media->IoAlign : 1;"""

LASTBLOCK_OLD = """  mVolumeMedia.LastBlock        = mVolumeBytes / RAM_BLOCK_SIZE - 1;"""

LASTBLOCK_NEW = """  mVolumeMedia.LastBlock        = mVolumeBytes / mVolumeMedia.BlockSize - 1;"""

WAIT_OLD = """  if (mVolumeReady) {
    Print (L"fastboot: payload volume published after %u ms\\n", (UINT32)Elapsed);"""

WAIT_NEW = """  //
  // Nothing came over USB. Take the copy the host wrote into the ipados
  // partition, if there is one: this is the only path left when the DWC3
  // controller never brings the device up.
  //
  if (!mVolumeReady) {
    if (!EFI_ERROR (PayloadFromDisk ()) && !EFI_ERROR (PublishVolume ())) {
      Print (L"fastboot: payload volume published from storage\\n");
    }
  }

  if (mVolumeReady) {
    Print (L"fastboot: payload volume published after %u ms\\n", (UINT32)Elapsed);"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="checkout of the uefi repository")
    args = parser.parse_args()

    path = pathlib.Path(args.root) / TARGET
    if not path.exists():
        print(f"!! {path}: not found", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if "PayloadFromDisk" in text:
        print(f"  {path}: already patched")
        return 0

    if GLOBALS_OLD not in text:
        print("  !! volume globals not found", file=sys.stderr)
        return 1
    text = text.replace(GLOBALS_OLD, GLOBALS_NEW, 1)

    if PUBLISH_ANCHOR not in text:
        print("  !! PublishVolume not found", file=sys.stderr)
        return 1
    text = text.replace(PUBLISH_ANCHOR, PUBLISH_ANCHOR, 1)

    for old, new, what in (
        (VOLREAD_OLD, VOLREAD_NEW, "volume read"),
        (CHECK_OLD, CHECK_NEW, "publish guard"),
        (BASE_OLD, BASE_NEW, "publish base"),
        (GEOM_OLD, GEOM_NEW, "publish geometry"),
        (LASTBLOCK_OLD, LASTBLOCK_NEW, "publish last block"),
        (WAIT_OLD, WAIT_NEW, "wait fallback"),
    ):
        if old not in text:
            print(f"  !! {what} anchor not found", file=sys.stderr)
            return 1
        text = text.replace(old, new, 1)

    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    print(f"  {path}: payload volume can come from storage")
    return 0


if __name__ == "__main__":
    sys.exit(main())