#!/usr/bin/env python3
"""
Repair a broken AIFF header after a Max/MSP crash mid-recording.

Max's sfrecord~ (and similar objects) writes a placeholder AIFF header
when recording starts, then goes back and patches in the correct chunk
sizes when recording stops cleanly. If Max crashes, that patch never
happens, so the FORM/COMM/SSND sizes are left at 0 (or some small
placeholder), even though all the audio data is sitting there on disk.

This script:
  1. Reads the existing header to confirm it's a standard AIFF/COMM/SSND
     layout (does NOT touch or move any audio data).
  2. Recalculates the correct chunk sizes from the actual file size and
     known format (sample rate / bit depth / channels).
  3. Writes a REPAIRED COPY with corrected header. Original file is
     never modified.

Usage:
    python3 repair_aiff.py "/path/to/broken.aif"

Optional overrides if auto-detection looks wrong:
    python3 repair_aiff.py "/path/to/broken.aif" --channels 2 --bits 24 --rate 48000
"""

import argparse
import struct
import shutil
import sys
from pathlib import Path


def read_chunks_header(data: bytes):
    """Parse FORM/COMM/SSND headers from the start of an AIFF file."""
    if data[0:4] != b'FORM':
        raise ValueError("Not a FORM/AIFF file (missing 'FORM' at offset 0)")
    if data[8:12] != b'AIFF':
        raise ValueError("Not an AIFF file (missing 'AIFF' at offset 8)")

    pos = 12
    comm_offset = None
    ssnd_offset = None
    channels = bits = rate = None
    num_frames = None

    while pos < len(data) - 8:
        chunk_id = data[pos:pos+4]
        chunk_size = struct.unpack('>I', data[pos+4:pos+8])[0]

        if chunk_id == b'COMM':
            comm_offset = pos
            channels = struct.unpack('>H', data[pos+8:pos+10])[0]
            num_frames = struct.unpack('>I', data[pos+10:pos+14])[0]
            bits = struct.unpack('>H', data[pos+14:pos+16])[0]
            # sample rate is an 80-bit IEEE extended float, we won't
            # bother decoding it since the user supplies rate directly
            pos += 8 + chunk_size + (chunk_size % 2)
        elif chunk_id == b'SSND':
            ssnd_offset = pos
            break  # audio data follows; stop parsing here
        else:
            pos += 8 + chunk_size + (chunk_size % 2)

    if comm_offset is None or ssnd_offset is None:
        raise ValueError("Could not find both COMM and SSND chunks")

    return {
        'comm_offset': comm_offset,
        'ssnd_offset': ssnd_offset,
        'channels': channels,
        'bits': bits,
        'num_frames_in_header': num_frames,
    }


def ieee_extended_from_rate(rate: int) -> bytes:
    """Encode an integer sample rate as an 80-bit IEEE-754 extended float,
    the format AIFF's COMM chunk requires."""
    if rate == 0:
        return b'\x00' * 10
    sign = 0
    exponent = 0
    f = float(rate)
    while f >= 1.0:
        f /= 2.0
        exponent += 1
    exponent += 16382
    f *= 2.0 ** 64
    mantissa = int(f)
    return struct.pack('>H', exponent) + struct.pack('>Q', mantissa)


def repair(path: Path, channels: int, bits: int, rate: int, out_path: Path):
    file_size = path.stat().st_size
    with open(path, 'rb') as f:
        header_preview = f.read(4096)  # plenty to find COMM/SSND

    info = read_chunks_header(header_preview)
    print(f"Found COMM chunk at offset {info['comm_offset']}")
    print(f"Found SSND chunk at offset {info['ssnd_offset']}")
    print(f"Header reports: channels={info['channels']}, bits={info['bits']}, "
          f"num_frames_in_header={info['num_frames_in_header']}")

    if info['channels'] and info['channels'] != channels:
        print(f"WARNING: header says {info['channels']} channels, "
              f"you specified {channels}. Using your value: {channels}")
    if info['bits'] and info['bits'] != bits:
        print(f"WARNING: header says {info['bits']}-bit, "
              f"you specified {bits}-bit. Using your value: {bits}")

    ssnd_offset = info['ssnd_offset']
    # SSND chunk layout: 'SSND' + size(4) + offset(4) + blockSize(4) + audio data
    ssnd_data_start = ssnd_offset + 8 + 8  # past 'SSND', size, offset, blockSize
    audio_data_size = file_size - ssnd_data_start

    bytes_per_frame = channels * (bits // 8)
    num_sample_frames = audio_data_size // bytes_per_frame
    remainder = audio_data_size % bytes_per_frame

    if remainder != 0:
        print(f"NOTE: {remainder} trailing bytes don't fit a whole frame "
              f"(partial frame at the very end, likely from the crash). "
              f"These will be left in place but excluded from the frame count.")

    duration_sec = num_sample_frames / rate
    print(f"\nCalculated: {num_sample_frames} frames, "
          f"{duration_sec:.2f} sec ({duration_sec/60:.2f} min) of audio")

    ssnd_chunk_size = audio_data_size + 8  # +8 for offset & blockSize fields
    form_chunk_size = file_size - 8

    # Read full original header block, patch it, write out
    with open(path, 'rb') as f:
        header_block = bytearray(f.read(ssnd_data_start))

    # Patch FORM size (bytes 4-8)
    header_block[4:8] = struct.pack('>I', form_chunk_size)

    # Patch COMM: only numSampleFrames needs fixing. channels, sampleSize,
    # and sampleRate are left exactly as Max originally wrote them, since
    # those were already correct (only the frame count was zeroed out).
    comm_off = info['comm_offset']
    header_block[comm_off+10:comm_off+14] = struct.pack('>I', num_sample_frames)

    # Patch SSND size
    header_block[ssnd_offset+4:ssnd_offset+8] = struct.pack('>I', ssnd_chunk_size)

    print(f"\nWriting repaired file to: {out_path}")
    with open(path, 'rb') as src, open(out_path, 'wb') as dst:
        dst.write(header_block)
        src.seek(ssnd_data_start)
        shutil.copyfileobj(src, dst, length=1024 * 1024)

    print("Done. Original file was not modified.")


def main():
    p = argparse.ArgumentParser(description="Repair a crashed Max/MSP AIFF recording")
    p.add_argument('input', type=str, help="Path to the broken .aif file")
    p.add_argument('--channels', type=int, default=2)
    p.add_argument('--bits', type=int, default=24)
    p.add_argument('--rate', type=int, default=48000)
    p.add_argument('--output', type=str, default=None,
                    help="Output path (default: adds _repaired before extension)")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"File not found: {in_path}")
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = in_path.with_name(in_path.stem + '_repaired' + in_path.suffix)

    try:
        repair(in_path, args.channels, args.bits, args.rate, out_path)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()