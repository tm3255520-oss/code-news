#!/usr/bin/env python3
"""Extract readable text from PPTX and legacy PPT files for source audits."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import stat
import struct
import sys
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

try:
    from .safe_io import (
        ensure_safe_directory,
        ensure_safe_input_file,
        read_bytes_no_follow,
        safe_write_text,
    )
except ImportError:
    from safe_io import (
        ensure_safe_directory,
        ensure_safe_input_file,
        read_bytes_no_follow,
        safe_write_text,
    )


END_OF_CHAIN = -2
FREE_SECTOR = -1
NO_STREAM = -1
CFB_HEADER_BYTES = 512
VALID_SECTOR_SHIFTS = {9, 12}
VALID_MINI_SECTOR_SHIFT = 6
MAX_PPT_RECORD_NESTING = 64
MAX_PPT_RECORDS = 1_000_000
MAX_PRESENTATION_INPUT_BYTES = 256 * 1024 * 1024
MAX_PPTX_ZIP_MEMBERS = 20_000
MAX_PPTX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_PPTX_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_PPTX_COMPRESSION_RATIO = 1000
REQUIRED_PPTX_PARTS = {"[Content_Types].xml", "ppt/presentation.xml"}
OUTPUT_DIR_ERROR_REASON = "--output-dir must be a directory without symlink components"

PLACEHOLDER_RE = re.compile(
    r"^(?:"
    r"\d+|"
    r"幻灯片\s*\d+|"
    r"单击此处编辑.*|"
    r"Click to edit.*|"
    r"Microsoft PowerPoint.*"
    r")$",
    re.I,
)


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(1 for char in text if char.isprintable() or char in "\r\n\t")
    return printable / len(text)


def clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", "")).strip()


def is_useful_line(text: str) -> bool:
    line = clean_line(text)
    if not line or PLACEHOLDER_RE.match(line):
        return False
    return any(char.isalnum() or "\u4e00" <= char <= "\u9fff" for char in line)


def cfb_sector_offset(sector_id: int, sector_size: int) -> int:
    return (sector_id + 1) * sector_size


def read_cfb_stream(path: Path, stream_name: str) -> bytes:
    path = ensure_safe_input_file(path)
    data = read_bytes_no_follow(path, max_bytes=MAX_PRESENTATION_INPUT_BYTES)
    if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError(f"not a Compound File Binary document: {path}")
    if len(data) < CFB_HEADER_BYTES:
        raise ValueError(f"truncated Compound File Binary header: {path}")

    sector_shift = struct.unpack_from("<H", data, 30)[0]
    mini_sector_shift = struct.unpack_from("<H", data, 32)[0]
    if sector_shift not in VALID_SECTOR_SHIFTS or mini_sector_shift != VALID_MINI_SECTOR_SHIFT:
        raise ValueError(f"unsupported Compound File Binary sector geometry: {path}")
    sector_size = 1 << sector_shift
    mini_sector_size = 1 << mini_sector_shift
    if len(data) < sector_size:
        raise ValueError(f"truncated Compound File Binary sector area: {path}")
    total_sectors = len(data) // sector_size - 1
    fat_sector_count = struct.unpack_from("<I", data, 44)[0]
    directory_start = struct.unpack_from("<i", data, 48)[0]
    mini_stream_cutoff = struct.unpack_from("<I", data, 56)[0]
    mini_fat_start = struct.unpack_from("<i", data, 60)[0]
    mini_fat_sector_count = struct.unpack_from("<I", data, 64)[0]
    difat_start = struct.unpack_from("<i", data, 68)[0]
    difat_sector_count = struct.unpack_from("<I", data, 72)[0]
    if any(count > total_sectors for count in (fat_sector_count, mini_fat_sector_count, difat_sector_count)):
        raise ValueError(f"Compound File Binary sector count exceeds file bounds: {path}")

    def sector_payload(sector_id: int) -> bytes:
        if sector_id < 0 or sector_id >= total_sectors:
            raise ValueError(f"Compound File Binary sector is outside file bounds: {sector_id}")
        offset = cfb_sector_offset(sector_id, sector_size)
        end = offset + sector_size
        if end > len(data):
            raise ValueError(f"truncated Compound File Binary sector: {sector_id}")
        return data[offset:end]

    difat = list(struct.unpack_from("<109i", data, 76))
    current = difat_start
    seen: set[int] = set()
    if difat_sector_count == 0 and current not in (END_OF_CHAIN, FREE_SECTOR, NO_STREAM):
        raise ValueError(f"Compound File Binary has a DIFAT start without DIFAT sectors: {path}")
    for _ in range(difat_sector_count):
        if current in (END_OF_CHAIN, FREE_SECTOR, NO_STREAM) or current in seen:
            raise ValueError(f"Compound File Binary DIFAT chain is shorter than declared: {path}")
        seen.add(current)
        entries = list(struct.unpack(f"<{sector_size // 4}i", sector_payload(current)))
        difat.extend(entries[:-1])
        current = entries[-1]

    fat_sectors = [sector for sector in difat if sector >= 0][:fat_sector_count]
    fat: list[int] = []
    for sector in fat_sectors:
        fat.extend(struct.unpack(f"<{sector_size // 4}i", sector_payload(sector)))

    def read_chain(start_sector: int) -> bytes:
        output = bytearray()
        sector = start_sector
        chain_seen: set[int] = set()
        while sector >= 0 and sector not in chain_seen:
            chain_seen.add(sector)
            output.extend(sector_payload(sector))
            if sector >= len(fat):
                break
            sector = fat[sector]
            if sector == END_OF_CHAIN:
                break
        return bytes(output)

    directory_data = read_chain(directory_start)
    entries: list[dict[str, int | str]] = []
    root_entry: dict[str, int | str] | None = None
    target_entry: dict[str, int | str] | None = None

    for offset in range(0, len(directory_data), 128):
        entry = directory_data[offset : offset + 128]
        if len(entry) < 128:
            continue
        name_length = struct.unpack_from("<H", entry, 64)[0]
        if name_length < 2:
            continue
        name = entry[: name_length - 2].decode("utf-16le", errors="ignore")
        entry_type = entry[66]
        start_sector = struct.unpack_from("<i", entry, 116)[0]
        size = struct.unpack_from("<Q", entry, 120)[0]
        item = {
            "name": name,
            "type": entry_type,
            "start": start_sector,
            "size": size,
        }
        entries.append(item)
        if entry_type == 5:
            root_entry = item
        if name == stream_name:
            target_entry = item

    if target_entry is None:
        raise KeyError(f"stream not found: {stream_name}")

    start = int(target_entry["start"])
    size = int(target_entry["size"])
    if size < mini_stream_cutoff and root_entry is not None:
        mini_fat = read_chain(mini_fat_start)[: mini_fat_sector_count * sector_size]
        mini_entries = list(struct.unpack_from(f"<{len(mini_fat) // 4}i", mini_fat, 0)) if mini_fat else []
        root_stream = read_chain(int(root_entry["start"]))[: int(root_entry["size"])]
        output = bytearray()
        mini_sector = start
        chain_seen: set[int] = set()
        while mini_sector >= 0 and mini_sector not in chain_seen:
            chain_seen.add(mini_sector)
            offset = mini_sector * mini_sector_size
            output.extend(root_stream[offset : offset + mini_sector_size])
            if mini_sector >= len(mini_entries):
                break
            mini_sector = mini_entries[mini_sector]
            if mini_sector == END_OF_CHAIN:
                break
        return bytes(output[:size])

    return read_chain(start)[:size]


def parse_ppt_records(
    payload: bytes | memoryview,
    output: list[str],
    *,
    _depth: int = 0,
    _record_budget: list[int] | None = None,
) -> None:
    if _depth > MAX_PPT_RECORD_NESTING:
        raise ValueError("legacy PPT record nesting exceeds safety limit")
    if _record_budget is None:
        _record_budget = [MAX_PPT_RECORDS]
    payload = memoryview(payload)
    position = 0
    payload_length = len(payload)
    while position + 8 <= payload_length:
        instance_version, record_type, record_length = struct.unpack_from("<HHI", payload, position)
        _record_budget[0] -= 1
        if _record_budget[0] < 0:
            raise ValueError("legacy PPT record count exceeds safety limit")
        version = instance_version & 0xF
        start = position + 8
        end = start + record_length
        if end > payload_length:
            break
        body = payload[start:end]

        if record_type in (4000, 4026):
            text = body.tobytes().decode("utf-16le", errors="ignore")
            if printable_ratio(text) > 0.65:
                for line in text.splitlines():
                    if is_useful_line(line):
                        output.append(clean_line(line))
        elif record_type == 4008:
            for encoding in ("gbk", "cp1252", "utf-8"):
                text = body.tobytes().decode(encoding, errors="ignore")
                if printable_ratio(text) > 0.65:
                    for line in text.splitlines():
                        if is_useful_line(line):
                            output.append(clean_line(line))
                    break

        if version == 0xF and record_length:
            parse_ppt_records(
                body,
                output,
                _depth=_depth + 1,
                _record_budget=_record_budget,
            )
        position = end


def extract_ppt(path: Path) -> str:
    stream = read_cfb_stream(path, "PowerPoint Document")
    lines: list[str] = []
    parse_ppt_records(stream, lines)
    return join_deduped(lines)


def slide_number(path: str) -> tuple[int, str]:
    match = re.search(r"slide(\d+)\.xml$", path)
    return (int(match.group(1)) if match else 0, path)


def extract_text_from_xml(xml_data: bytes) -> list[str]:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []
    lines: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text and is_useful_line(node.text):
            lines.append(clean_line(node.text))
    return lines


def extract_pptx(path: Path) -> str:
    path = ensure_safe_input_file(path)
    data = read_bytes_no_follow(path, max_bytes=MAX_PRESENTATION_INPUT_BYTES)
    sections: list[str] = []
    with zipfile.ZipFile(BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > MAX_PPTX_ZIP_MEMBERS:
            raise ValueError("PPTX ZIP package has too many members")
        names: set[str] = set()
        total = 0
        for member in members:
            if member.filename in names:
                raise ValueError("PPTX ZIP package contains duplicate members")
            names.add(member.filename)
            if member.flag_bits & 0x1:
                raise ValueError("encrypted PPTX packages are not supported")
            if member.file_size > MAX_PPTX_MEMBER_BYTES:
                raise ValueError("PPTX ZIP member exceeds the uncompressed size limit")
            total += member.file_size
            if total > MAX_PPTX_TOTAL_UNCOMPRESSED_BYTES:
                raise ValueError("PPTX ZIP package exceeds the total uncompressed size limit")
            if member.file_size and (
                member.compress_size == 0
                or member.file_size > member.compress_size * MAX_PPTX_COMPRESSION_RATIO
            ):
                raise ValueError("PPTX ZIP member exceeds the compression-ratio limit")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ValueError(f"PPTX ZIP package has a corrupt member: {corrupt}")
        names = {member.filename for member in members}
        if not REQUIRED_PPTX_PARTS <= names:
            raise ValueError("PPTX package is missing required OOXML parts")
        try:
            for name in REQUIRED_PPTX_PARTS:
                ET.fromstring(archive.read(name))
        except ET.ParseError:
            raise ValueError("PPTX package contains malformed required XML") from None
        slide_names = sorted(
            (name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
            key=slide_number,
        )
        for index, name in enumerate(slide_names, start=1):
            lines = extract_text_from_xml(archive.read(name))
            if lines:
                sections.append(f"--- Slide {index} ---")
                sections.extend(lines)
    return join_deduped(sections)


def join_deduped(lines: list[str]) -> str:
    output: list[str] = []
    previous = ""
    for line in lines:
        cleaned = clean_line(line)
        if not cleaned or cleaned == previous:
            continue
        output.append(cleaned)
        previous = cleaned
    return "\n".join(output).strip() + "\n"


def extract(path: Path) -> str:
    path = ensure_safe_input_file(path)
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        return extract_pptx(path)
    if suffix == ".ppt":
        return extract_ppt(path)
    raise ValueError(f"unsupported presentation extension: {path.suffix}")


def render_extraction(path: Path) -> str:
    """Wrap fallback text hints in explicit non-source coverage metadata."""

    if path.suffix.lower() == ".pptx":
        backend = "pptx-zip-slide-xml-text"
        speaker_notes = "not extracted by this PPTX fallback"
    elif path.suffix.lower() == ".ppt":
        backend = "legacy-ppt-ole-cfb-text-records"
        speaker_notes = "not reliably distinguished or covered by this legacy fallback"
    else:
        raise ValueError(f"unsupported presentation extension: {path.suffix}")
    header = [
        "=== EXTRACTION METADATA (NOT SOURCE TEXT) ===",
        f"Source: {path}",
        f"Backend: {backend}",
        "Coverage: partial text hints only; this is not complete slide coverage.",
        "Visual/OCR coverage: none; images, charts, equations, layout, and other visual meaning may be missing.",
        f"Speaker notes coverage: {speaker_notes}.",
        "=== EXTRACTED TEXT HINTS ===",
        "",
    ]
    return "\n".join(header) + extract(path)


def output_path_for(source: Path, output_dir: Path) -> Path:
    stem = re.sub(r"[\s/]+", "_", source.stem).strip("_")
    return output_dir / f"{stem}.txt"


def output_name_key(value: str) -> str:
    """Model case-insensitive, canonically normalizing destination filesystems."""

    return unicodedata.normalize("NFC", value).casefold()


def allocate_output_paths(sources: list[Path], output_dir: Path) -> list[Path]:
    """Allocate stable output names without overwriting same-basename sources.

    Preserve the familiar <stem>.txt name when it is unique.  When basenames
    collide case-insensitively, append a short hash of the resolved source path
    to every colliding name.  A deterministic numeric suffix handles duplicate
    arguments or the extremely unlikely case of a hash collision.
    """

    default_paths = [output_path_for(source, output_dir) for source in sources]
    basename_counts = Counter(output_name_key(path.name) for path in default_paths)
    allocated: list[Path] = []
    used_names: set[str] = set()

    for source, default_path in zip(sources, default_paths):
        candidate = default_path
        if basename_counts[output_name_key(default_path.name)] > 1:
            identity = source.expanduser().resolve().as_posix()
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
            candidate = output_dir / f"{default_path.stem}--{digest}{default_path.suffix}"

        if output_name_key(candidate.name) in used_names:
            index = 2
            while True:
                numbered = candidate.with_name(f"{candidate.stem}--{index}{candidate.suffix}")
                if output_name_key(numbered.name) not in used_names:
                    candidate = numbered
                    break
                index += 1

        used_names.add(output_name_key(candidate.name))
        allocated.append(candidate)

    return allocated


def ensure_safe_output_path(output_dir: Path, path: Path) -> Path:
    output_root = Path(os.path.abspath(output_dir.expanduser()))
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(f"generated output escapes --output-dir: {path}") from exc
    candidate = output_root / relative
    try:
        mode = candidate.lstat().st_mode
    except FileNotFoundError:
        return candidate
    if stat.S_ISLNK(mode):
        raise ValueError(f"generated output path is a symlink: {candidate}")
    if not stat.S_ISREG(mode):
        raise ValueError(f"generated output path is not a regular file: {candidate}")
    return candidate


def write_text_no_follow(output_dir: Path, path: Path, content: str) -> None:
    candidate = ensure_safe_output_path(output_dir, path)
    safe_write_text(candidate, content)


def main() -> int:
    configure_output_encoding()
    parser = argparse.ArgumentParser(description="Extract text from PPTX and legacy PPT files.")
    parser.add_argument("sources", nargs="+", type=Path, help="PPT or PPTX files")
    parser.add_argument("--output-dir", type=Path, help="write one .txt file per source")
    args = parser.parse_args()

    try:
        args.sources = [ensure_safe_input_file(source) for source in args.sources]
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output_dir:
        requested_output_dir = args.output_dir.expanduser()
        try:
            args.output_dir = ensure_safe_directory(
                requested_output_dir,
                create=True,
            )
            output_paths = [
                ensure_safe_output_path(args.output_dir, path)
                for path in allocate_output_paths(args.sources, args.output_dir)
            ]
        except (OSError, ValueError):
            print(
                f"ERROR: {requested_output_dir}: {OUTPUT_DIR_ERROR_REASON}",
                file=sys.stderr,
            )
            return 1
    else:
        output_paths = [None] * len(args.sources)

    exit_code = 0
    for source, target in zip(args.sources, output_paths):
        try:
            extracted_text = render_extraction(source)
            if target is not None:
                write_text_no_follow(args.output_dir, target, extracted_text)
                print(f"wrote {target} source={source}")
            else:
                print(f"===== {source} =====")
                print(extracted_text, end="")
        except Exception as exc:
            print(f"ERROR: {source}: {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
