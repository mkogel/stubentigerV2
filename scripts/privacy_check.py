#!/usr/bin/env python3
"""Reject files that must not reach the public repo.

A file fails when its path matches the .gitignore deny-list (so a force-add
is caught too), or when it is an image whose metadata carries GPS data or a
camera serial number. Runs as a pre-commit hook on the given paths and is
imported by the Claude Code guard (.claude/hooks/guard.py) to check outgoing
commits. Standard library only. See CLAUDE.md, "Public repo".
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif", ".avif", ".dng"}
)

GPS_IFD_POINTER = 0x8825
EXIF_IFD_POINTER = 0x8769
SERIAL_TAGS = {
    0xA431: "BodySerialNumber",
    0xA435: "LensSerialNumber",
    0xC62F: "CameraSerialNumber",
}
XMP_MARKERS = (b"GPSLatitude", b"GPSLongitude", b"SerialNumber")

FIX_HINT = "strip the metadata first, e.g. `exiftool -all= <file>`, or re-export without it"


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def denied_paths(paths: list[str], repo: str | Path = ".") -> list[str]:
    """Return the paths that match the .gitignore deny-list, tracked or not."""
    if not paths:
        return []
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin", "-z"],
        cwd=repo,
        input="\0".join(paths) + "\0",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git check-ignore failed: {result.stderr.strip()}")
    return [p for p in result.stdout.split("\0") if p]


def image_findings(data: bytes) -> list[str]:
    """Return the private metadata found in an image's bytes (empty when clean)."""
    findings: set[str] = set()
    for tiff in _tiff_blocks(data):
        findings.update(_tiff_findings(tiff))
    for marker in XMP_MARKERS:
        if marker in data:
            findings.add(f"XMP {marker.decode()}")
    return sorted(findings)


def _tiff_blocks(data: bytes) -> list[bytes]:
    blocks = []
    if data[:4] in (b"II*\x00", b"MM\x00*"):  # TIFF, DNG
        blocks.append(data)
    start = 0
    while (i := data.find(b"Exif\x00\x00", start)) != -1:  # JPEG APP1, HEIC, AVIF, WebP
        blocks.append(data[i + 6 :])
        start = i + 6
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        blocks.extend(_png_chunks(data, b"eXIf"))
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        blocks.extend(c for c in _riff_chunks(data, b"EXIF") if not c.startswith(b"Exif"))
    return [b for b in blocks if b[:4] in (b"II*\x00", b"MM\x00*")]


def _png_chunks(data: bytes, wanted: bytes) -> list[bytes]:
    chunks, pos = [], 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        if kind == wanted:
            chunks.append(data[pos + 8 : pos + 8 + length])
        pos += 12 + length
    return chunks


def _riff_chunks(data: bytes, wanted: bytes) -> list[bytes]:
    chunks, pos = [], 12
    while pos + 8 <= len(data):
        kind, length = struct.unpack("<4sI", data[pos : pos + 8])
        if kind == wanted:
            chunks.append(data[pos + 8 : pos + 8 + length])
        pos += 8 + length + (length & 1)
    return chunks


def _tiff_findings(tiff: bytes) -> set[str]:
    endian = "<" if tiff[:2] == b"II" else ">"
    findings: set[str] = set()
    seen: set[int] = set()

    def read_ifd(offset: int) -> tuple[dict[int, tuple[int, int, bytes]], int]:
        """Return {tag: (type, count, raw value/offset field)} and the next-IFD offset."""
        if offset in seen or offset + 2 > len(tiff):
            return {}, 0
        seen.add(offset)
        (count,) = struct.unpack(endian + "H", tiff[offset : offset + 2])
        if count > 1000 or offset + 2 + 12 * count + 4 > len(tiff):
            return {}, 0
        entries = {}
        for n in range(count):
            at = offset + 2 + 12 * n
            tag, kind, num = struct.unpack(endian + "HHI", tiff[at : at + 8])
            entries[tag] = (kind, num, tiff[at + 8 : at + 12])
        (next_ifd,) = struct.unpack(
            endian + "I", tiff[offset + 2 + 12 * count : offset + 6 + 12 * count]
        )
        return entries, next_ifd

    def pointer(field: bytes) -> int:
        return int(struct.unpack(endian + "I", field)[0])

    def check(entries: dict[int, tuple[int, int, bytes]]) -> None:
        for tag, name in SERIAL_TAGS.items():
            if tag in entries and entries[tag][1] > 1:  # more than an empty string
                findings.add(f"EXIF {name}")
        if GPS_IFD_POINTER in entries:
            gps, _ = read_ifd(pointer(entries[GPS_IFD_POINTER][2]))
            if any(tag != 0 for tag in gps):  # anything beyond GPSVersionID
                findings.add("EXIF GPS data")
        if EXIF_IFD_POINTER in entries:
            exif, _ = read_ifd(pointer(entries[EXIF_IFD_POINTER][2]))
            check(exif)

    (offset,) = struct.unpack(endian + "I", tiff[4:8])
    while offset:
        entries, offset = read_ifd(offset)
        check(entries)
    return findings


def check_files(paths: list[str], repo: str | Path = ".") -> list[str]:
    """Return one problem line per failing file on disk."""
    problems = [
        f"{p}: matches the private-data deny-list in .gitignore" for p in denied_paths(paths, repo)
    ]
    for p in paths:
        if is_image(p) and Path(repo, p).is_file():
            found = image_findings(Path(repo, p).read_bytes())
            if found:
                problems.append(f"{p}: image metadata carries {', '.join(found)}; {FIX_HINT}")
    return problems


def main(argv: list[str]) -> int:
    problems = check_files(argv)
    for line in problems:
        print(line, file=sys.stderr)
    if problems:
        print("Blocked: this repo is public. See CLAUDE.md, 'Public repo'.", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
