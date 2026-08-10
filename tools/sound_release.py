#!/usr/bin/env python3
"""Build and validate deterministic Atrinik sound release artifacts."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import wave
from datetime import datetime


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "manifests" / "source-assets.json"
TOOLCHAIN = ROOT / "manifests" / "audio-toolchain.json"
FIXTURE_PLAN = ROOT / "manifests" / "fixture-plan.json"
QUALITY_REVIEWS = ROOT / "manifests" / "vorbis-quality-reviews.json"
LICENSE_REVIEWS = ROOT / "manifests" / "license-reviews.json"
TRACKER_DURATIONS = ROOT / "manifests" / "tracker-durations.json"
SCHEMA_ROOT = ROOT / "schemas"
AUDIO_SUFFIXES = {".mid", ".mod", ".s3m", ".xm", ".ogg"}
TRACKER_SUFFIXES = {".mod", ".s3m", ".xm"}
FIXTURE_PATHS = (
    "background/fireside.mid",
    "background/town.mod",
    "background/rain.s3m",
    "background/cave.xm",
    "background/crystal_falls.ogg",
    "effects/campfire.ogg",
)
REVIEWED_NOTICE_LICENSES = {
    'KQ - http://sourceforge.net/projects/kqlives/ - GPLv2': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'Meritous - http://www.asceai.net/meritous/ - GPLv3': ("GPL-3.0-only", "licenses/GPL-3.0.txt"),
    'http://piano-midi.de/ - CC BY-SA 3.0': ("CC-BY-SA-3.0", "licenses/CC-BY-SA-3.0.txt"),
    'Edwin "Mamoru" Miltenburg - GPLv2': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'http://sites.google.com/site/metaruka/GameGame - CC BY-SA 3.0': ("CC-BY-SA-3.0", "licenses/CC-BY-SA-3.0.txt"),
    'Allacrost - http://allacrost.org/ - GPLv2': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'Ecrivain - http://opengameart.org/users/Ecrivain - CC0': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'Brandon Morris - http://opengameart.org/users/brandon-morris - CC-BY 3.0': ("CC-BY-3.0", "licenses/CC-BY-3.0.txt"),
    'Yo Frankie! - http://www.yofrankie.org/ - CC-BY 3.0': ("CC-BY-3.0", "licenses/CC-BY-3.0.txt"),
    'Gobusto - http://opengameart.org/users/gobusto - CC-BY-SA 3.0': ("CC-BY-SA-3.0", "licenses/CC-BY-SA-3.0.txt"),
    'GNU FreeDink - http://www.freedink.org/ - GPLv3': ("GPL-3.0-only", "licenses/GPL-3.0.txt"),
    'Daniel "Lippy" Liptrot - CC-BY-SA 3.0': ("CC-BY-SA-3.0", "licenses/CC-BY-SA-3.0.txt"),
    'OpenTTD OpenMSX - http://wiki.openttd.org/OpenMSX - GPLv2': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'ZhayTee - http://www.zhaymusic.com/ - GPLv2': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'Jute - http://alturl.com/quao - GNU GPL 2.0': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'Ulrich Metzner - http://commons.wikimedia.org/wiki/User:Metzner - CC-BY-SA 3.0': ("CC-BY-SA-3.0", "licenses/CC-BY-SA-3.0.txt"),
    'n3b - http://opengameart.org/users/n3b - CC-BY 3.0': ("CC-BY-3.0", "licenses/CC-BY-3.0.txt"),
    'AuraVoice / Nocturnal_Vanguard - https://opengameart.org/content/female-hurt-grunts-groans - CC0': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'http://opengameart.org/content/4-atmospheric-ghostly-loops - CC0': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'free-loops.com - CC0': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'Mumu - http://opengameart.org/users/mumu - CC0 (Public Domain)': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'Ogrebane - http://opengameart.org/users/ogrebane - CC0 (Public Domain)': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'Jute - http://opengameart.org/users/qubodup - GNU GPL 2.0': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'kurt - http://opengameart.org/users/kurt - CC-BY 3.0': ("CC-BY-3.0", "licenses/CC-BY-3.0.txt"),
}


class ReleaseError(RuntimeError):
    """A release contract violation with an operator-facing diagnostic."""


@dataclasses.dataclass(frozen=True)
class SourceMetadata:
    duration_seconds: float
    sample_rate: int | None
    channels: int | None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_file())):
        digest.update(f"{sha256(path)}  {path}\n".encode("utf-8"))
    return digest.hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read JSON contract {path}: {exc}") from exc


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def checked_schema(name: str) -> dict[str, object]:
    value = read_json(SCHEMA_ROOT / name)
    expected_id = f"https://atrinik.org/schemas/sound/{name}"
    if not isinstance(value, dict) or value.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or value.get("$id") != expected_id:
        raise ReleaseError(f"invalid project schema: {name}")
    return value


def validate_schema_instance(instance: object, schema: dict[str, object], *, root: dict[str, object] | None = None, location: str = "$") -> None:
    root = schema if root is None else root
    reference = schema.get("$ref")
    if isinstance(reference, str):
        if not reference.startswith("#/$defs/"):
            raise ReleaseError(f"unsupported schema reference at {location}: {reference}")
        target: object = root
        for part in reference[2:].split("/"):
            if not isinstance(target, dict) or part not in target:
                raise ReleaseError(f"unresolved schema reference at {location}: {reference}")
            target = target[part]
        if not isinstance(target, dict):
            raise ReleaseError(f"invalid schema reference at {location}: {reference}")
        validate_schema_instance(instance, target, root=root, location=location)
        return
    choices = schema.get("oneOf")
    if isinstance(choices, list):
        matches = 0
        for choice in choices:
            try:
                if isinstance(choice, dict):
                    validate_schema_instance(instance, choice, root=root, location=location)
                    matches += 1
            except ReleaseError:
                pass
        if matches != 1:
            raise ReleaseError(f"schema oneOf mismatch at {location}")
        return
    if "const" in schema and instance != schema["const"]:
        raise ReleaseError(f"schema const mismatch at {location}")
    if isinstance(schema.get("enum"), list) and instance not in schema["enum"]:
        raise ReleaseError(f"schema enum mismatch at {location}")
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected] if isinstance(expected, str) else []
    checks = {"object": lambda value: isinstance(value, dict), "array": lambda value: isinstance(value, list), "string": lambda value: isinstance(value, str), "integer": lambda value: isinstance(value, int) and not isinstance(value, bool), "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool), "boolean": lambda value: isinstance(value, bool), "null": lambda value: value is None}
    if types and not any(checks[kind](instance) for kind in types):
        raise ReleaseError(f"schema type mismatch at {location}")
    if isinstance(instance, dict):
        required = schema.get("required", [])
        if isinstance(required, list) and any(key not in instance for key in required):
            raise ReleaseError(f"schema required field missing at {location}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ReleaseError(f"invalid schema properties at {location}")
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            child = properties.get(key)
            if isinstance(child, dict):
                validate_schema_instance(value, child, root=root, location=f"{location}.{key}")
            elif additional is False:
                raise ReleaseError(f"unknown schema field at {location}.{key}")
            elif isinstance(additional, dict):
                validate_schema_instance(value, additional, root=root, location=f"{location}.{key}")
        minimum_properties = schema.get("minProperties")
        if isinstance(minimum_properties, int) and len(instance) < minimum_properties:
            raise ReleaseError(f"too few properties at {location}")
    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(instance):
                validate_schema_instance(value, items, root=root, location=f"{location}[{index}]")
        if schema.get("uniqueItems") is True and len({json.dumps(value, sort_keys=True) for value in instance}) != len(instance):
            raise ReleaseError(f"duplicate schema items at {location}")
        minimum_items = schema.get("minItems")
        if isinstance(minimum_items, int) and len(instance) < minimum_items:
            raise ReleaseError(f"too few items at {location}")
    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, instance) is None:
            raise ReleaseError(f"schema pattern mismatch at {location}")
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(instance) < minimum_length:
            raise ReleaseError(f"schema string too short at {location}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if isinstance(schema.get("minimum"), (int, float)) and instance < schema["minimum"]:
            raise ReleaseError(f"schema minimum violation at {location}")
        if isinstance(schema.get("exclusiveMinimum"), (int, float)) and instance <= schema["exclusiveMinimum"]:
            raise ReleaseError(f"schema exclusive minimum violation at {location}")
        if isinstance(schema.get("maximum"), (int, float)) and instance > schema["maximum"]:
            raise ReleaseError(f"schema maximum violation at {location}")


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def discover_sources() -> list[Path]:
    sources: list[Path] = []
    for directory in (ROOT / "background", ROOT / "effects"):
        for path in directory.rglob("*"):
            if path.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            if path.is_symlink() or not path.is_file():
                raise ReleaseError(
                    f"audio source must be a regular non-symlink file: {path.relative_to(ROOT)}"
                )
            sources.append(path)
    return sorted(sources, key=lambda path: path.relative_to(ROOT).as_posix())


def ensure_sources_tracked(sources: list[Path]) -> None:
    try:
        completed = run(["git", "ls-files", "-z", "--", "background", "effects"], capture=True)
    except ReleaseError as exc:
        if os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") == "1" and not git_metadata_available():
            return
        raise ReleaseError("audio source tracking cannot be verified without Git metadata") from exc
    tracked = set(completed.stdout.rstrip("\0").split("\0"))
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in sources
        if path.relative_to(ROOT).as_posix() not in tracked
    ]
    if missing:
        raise ReleaseError(f"audio sources are not Git-tracked: {', '.join(missing)}")


def _read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ReleaseError("truncated MIDI variable-length quantity")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    raise ReleaseError("invalid MIDI variable-length quantity")


def midi_metadata(path: Path) -> SourceMetadata:
    data = path.read_bytes()
    if len(data) < 14 or data[:4] != b"MThd":
        raise ReleaseError(f"invalid MIDI header: {path.relative_to(ROOT)}")
    header_size = struct.unpack_from(">I", data, 4)[0]
    if header_size < 6 or 8 + header_size > len(data):
        raise ReleaseError(f"invalid MIDI header length: {path.relative_to(ROOT)}")
    _format, track_count, division = struct.unpack_from(">HHH", data, 8)
    if division & 0x8000:
        raise ReleaseError(f"SMPTE MIDI timing is unsupported: {path.relative_to(ROOT)}")
    if division == 0:
        raise ReleaseError(f"zero MIDI timing division: {path.relative_to(ROOT)}")

    cursor = 8 + header_size
    events: list[tuple[int, int | None]] = []
    maximum_tick = 0
    for _ in range(track_count):
        if cursor + 8 > len(data) or data[cursor : cursor + 4] != b"MTrk":
            raise ReleaseError(f"invalid MIDI track header: {path.relative_to(ROOT)}")
        size = struct.unpack_from(">I", data, cursor + 4)[0]
        track = data[cursor + 8 : cursor + 8 + size]
        if len(track) != size:
            raise ReleaseError(f"truncated MIDI track: {path.relative_to(ROOT)}")
        cursor += 8 + size
        offset = 0
        tick = 0
        running_status: int | None = None
        while offset < len(track):
            delta, offset = _read_vlq(track, offset)
            tick += delta
            maximum_tick = max(maximum_tick, tick)
            if offset >= len(track):
                raise ReleaseError(f"truncated MIDI event: {path.relative_to(ROOT)}")
            status = track[offset]
            if status < 0x80:
                if running_status is None:
                    raise ReleaseError(f"invalid MIDI running status: {path.relative_to(ROOT)}")
                status = running_status
            else:
                offset += 1
                if status < 0xF0:
                    running_status = status
            if status == 0xFF:
                if offset >= len(track):
                    raise ReleaseError(f"truncated MIDI meta event: {path.relative_to(ROOT)}")
                kind = track[offset]
                offset += 1
                length, offset = _read_vlq(track, offset)
                payload = track[offset : offset + length]
                if len(payload) != length:
                    raise ReleaseError(f"truncated MIDI meta payload: {path.relative_to(ROOT)}")
                offset += length
                if kind == 0x51 and length == 3:
                    events.append((tick, int.from_bytes(payload, "big")))
            elif status in (0xF0, 0xF7):
                length, offset = _read_vlq(track, offset)
                offset += length
            else:
                message = status & 0xF0
                width = 1 if message in (0xC0, 0xD0) else 2
                offset += width
            if offset > len(track):
                raise ReleaseError(f"truncated MIDI message: {path.relative_to(ROOT)}")

    tempo = 500_000
    previous_tick = 0
    elapsed_microseconds = 0.0
    for tick, new_tempo in sorted(events, key=lambda item: item[0]):
        elapsed_microseconds += (tick - previous_tick) * tempo / division
        previous_tick = tick
        if new_tempo is not None:
            tempo = new_tempo
    elapsed_microseconds += (maximum_tick - previous_tick) * tempo / division
    return SourceMetadata(round(elapsed_microseconds / 1_000_000, 6), None, None)


def ogg_vorbis_metadata(path: Path) -> SourceMetadata:
    data = path.read_bytes()
    offset = 0
    serial: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    last_granule = 0
    packet = bytearray()
    while offset < len(data):
        if not data[offset:].strip(b"\x00\t\n\r "):
            break
        if offset + 27 > len(data) or data[offset : offset + 4] != b"OggS":
            raise ReleaseError(f"invalid Ogg page at byte {offset}: {path.relative_to(ROOT)}")
        version = data[offset + 4]
        if version != 0:
            raise ReleaseError(f"unsupported Ogg version in {path.relative_to(ROOT)}")
        granule = struct.unpack_from("<Q", data, offset + 6)[0]
        page_serial = struct.unpack_from("<I", data, offset + 14)[0]
        segment_count = data[offset + 26]
        table_end = offset + 27 + segment_count
        if table_end > len(data):
            raise ReleaseError(f"truncated Ogg segment table: {path.relative_to(ROOT)}")
        sizes = data[offset + 27 : table_end]
        payload_end = table_end + sum(sizes)
        if payload_end > len(data):
            raise ReleaseError(f"truncated Ogg payload: {path.relative_to(ROOT)}")
        payload_offset = table_end
        if serial is None:
            serial = page_serial
        if page_serial == serial:
            if granule != 0xFFFFFFFFFFFFFFFF:
                last_granule = max(last_granule, granule)
            for size in sizes:
                packet.extend(data[payload_offset : payload_offset + size])
                payload_offset += size
                if size < 255:
                    if sample_rate is None:
                        if len(packet) < 16 or packet[:7] != b"\x01vorbis":
                            raise ReleaseError(f"first Ogg stream is not Vorbis: {path.relative_to(ROOT)}")
                        channels = packet[11]
                        sample_rate = struct.unpack_from("<I", packet, 12)[0]
                    packet.clear()
        offset = payload_end
    if not sample_rate or not channels or not last_granule:
        raise ReleaseError(f"incomplete Vorbis metadata: {path.relative_to(ROOT)}")
    return SourceMetadata(round(last_granule / sample_rate, 6), sample_rate, channels)


def checked_tracker_durations() -> dict[str, dict[str, object]]:
    schema = checked_schema("tracker-durations-v1.schema.json")
    value = read_json(TRACKER_DURATIONS)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "toolchain_sha256", "entries"} or value.get("schema_version") != 1 or value.get("toolchain_sha256") != sha256(TOOLCHAIN) or not isinstance(value.get("entries"), list):
        raise ReleaseError("tracker-duration ledger is invalid or stale")
    validate_schema_instance(value, schema)
    entries: dict[str, dict[str, object]] = {}
    for entry in value["entries"]:
        assert isinstance(entry, dict)
        logical = str(entry["logical_path"])
        if logical in entries:
            raise ReleaseError(f"duplicate tracker-duration entry: {logical}")
        entries[logical] = entry
    expected = {
        path.relative_to(ROOT).as_posix()
        for path in discover_sources()
        if path.suffix.lower() in TRACKER_SUFFIXES
    }
    if set(entries) != expected:
        missing = expected - set(entries)
        stale = set(entries) - expected
        detail = ", ".join([*(f"missing {path}" for path in sorted(missing)), *(f"stale {path}" for path in sorted(stale))])
        raise ReleaseError(f"tracker-duration ledger does not close over tracker sources: {detail}")
    for logical, entry in entries.items():
        if entry.get("source_sha256") != sha256(ROOT / logical):
            raise ReleaseError(f"tracker-duration source hash is stale: {logical}")
    return entries


def tracker_metadata(path: Path) -> SourceMetadata:
    entries = checked_tracker_durations()
    relative = path.relative_to(ROOT).as_posix()
    entry = entries[relative]
    duration = float(entry["duration_seconds"])
    if not math.isfinite(duration) or duration <= 0:
        raise ReleaseError(f"non-positive tracker duration for {path.relative_to(ROOT)}")
    return SourceMetadata(duration, None, None)


def ensure_clean_release_input() -> None:
    try:
        status = run(["git", "status", "--porcelain", "--untracked-files=all"], capture=True).stdout
    except ReleaseError as exc:
        if os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") != "1" or git_metadata_available():
            raise ReleaseError(
                "full runtime release requires a host-validated input attestation when Git metadata is unavailable"
            ) from exc
        return
    if status:
        raise ReleaseError("full runtime release input worktree is not clean")


def measured_tracker_duration(path: Path) -> float:
    completed = run(["openmpt123", "--info", str(path)], capture=True)
    match = re.search(r"^Duration\.\.\.: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$", completed.stdout + completed.stderr, re.MULTILINE)
    if match is None:
        raise ReleaseError(f"cannot parse pinned openmpt123 duration: {path.relative_to(ROOT)}")
    hours = int(match.group(1) or 0)
    duration = hours * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    if not math.isfinite(duration) or duration <= 0:
        raise ReleaseError(f"non-positive tracker duration for {path.relative_to(ROOT)}")
    return round(duration, 6)


def source_metadata(path: Path) -> SourceMetadata:
    suffix = path.suffix.lower()
    if suffix == ".ogg":
        return ogg_vorbis_metadata(path)
    if suffix == ".mid":
        return midi_metadata(path)
    if suffix in TRACKER_SUFFIXES:
        return tracker_metadata(path)
    raise ReleaseError(f"unsupported source format: {path.relative_to(ROOT)}")


def notice_catalog(directory: Path) -> dict[str, dict[str, str]]:
    license_path = directory / "LICENSE"
    lines = license_path.read_text(encoding="utf-8").splitlines()
    current = ""
    notices: dict[str, dict[str, str]] = {}
    for line_number, line in enumerate(lines, 1):
        if line and not line[0].isspace() and line.endswith(":"):
            current = line[:-1]
            continue
        match = re.match(r"^\s{4}([A-Za-z0-9_.-]+\.(?:mid|mod|s3m|xm|ogg))\b", line)
        if match and current:
            filename = match.group(1)
            if filename in notices:
                raise ReleaseError(f"duplicate notice for {directory.name}/{filename}")
            notices[filename] = {
                "description": current,
                "reference": f"{directory.name}/LICENSE:{line_number}",
            }
    return notices


def notice_status(
    notice: dict[str, str] | None,
) -> tuple[str, str | None, str | None, str | None]:
    if notice is None:
        return "blocked", "missing exact asset notice", None, None
    reviewed = REVIEWED_NOTICE_LICENSES.get(notice["description"])
    if reviewed is None:
        return (
            "blocked",
            "notice has no reviewed full-work conversion and redistribution grant",
            None,
            None,
        )
    expression, license_text_path = reviewed
    return "candidate", "per-asset license review evidence is missing", expression, license_text_path


def verify_review_evidence(evidence: dict[str, object], logical_path: str) -> None:
    locator = evidence.get("artifact_locator", evidence.get("locator"))
    pure = PurePosixPath(str(locator))
    if not isinstance(locator, str) or not locator.startswith("evidence/") or pure.is_absolute() or ".." in pure.parts or pure.as_posix() != locator:
        raise ReleaseError(f"review evidence locator is unsafe or not repository-owned: {logical_path}")
    path = ROOT / locator
    if path.is_symlink() or not path.is_file():
        raise ReleaseError(f"review evidence is missing or not a regular file: {logical_path}")
    try:
        run(["git", "ls-files", "--error-unmatch", "--", locator], capture=True)
    except ReleaseError as exc:
        if os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") != "1" or git_metadata_available():
            raise ReleaseError(f"review evidence is not Git-tracked: {logical_path}") from exc
    if sha256(path) != evidence.get("artifact_sha256", evidence.get("sha256")):
        raise ReleaseError(f"review evidence hash mismatch: {logical_path}")


def checked_quality_reviews() -> dict[str, dict[str, object]]:
    schema = checked_schema("vorbis-quality-reviews-v1.schema.json")
    value = read_json(QUALITY_REVIEWS)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "reviews"} or value.get("$schema") != "../schemas/vorbis-quality-reviews-v1.schema.json" or value.get("schema_version") != 1:
        raise ReleaseError("Vorbis quality-review root must use schema version 1")
    entries = value.get("reviews")
    if not isinstance(entries, list):
        raise ReleaseError("Vorbis quality reviews must be an array")
    validate_schema_instance(value, schema)
    reviews: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "logical_path", "status", "source_sha256", "toolchain_sha256",
            "output_sha256", "reviewed_by", "reviewed_at", "evidence",
        } or not isinstance(entry.get("logical_path"), str):
            raise ReleaseError("invalid Vorbis quality-review entry")
        logical_path = str(entry["logical_path"])
        if logical_path in reviews:
            raise ReleaseError(f"duplicate Vorbis quality review: {logical_path}")
        if entry.get("status") != "passed":
            raise ReleaseError(f"quality review is not passed: {logical_path}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("source_sha256", ""))):
            raise ReleaseError(f"quality review lacks a source hash: {logical_path}")
        if entry.get("toolchain_sha256") != sha256(TOOLCHAIN):
            raise ReleaseError(f"quality review has a stale toolchain hash: {logical_path}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("output_sha256", ""))):
            raise ReleaseError(f"quality review lacks an output hash: {logical_path}")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", str(entry.get("reviewed_by", ""))):
            raise ReleaseError(f"quality review lacks a GitHub reviewer identity: {logical_path}")
        reviewed_at = entry.get("reviewed_at")
        try:
            if not isinstance(reviewed_at, str) or datetime.strptime(reviewed_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != reviewed_at:
                raise ValueError
        except ValueError as exc:
            raise ReleaseError(f"quality review has a non-canonical UTC timestamp: {logical_path}") from exc
        evidence = entry.get("evidence")
        if not isinstance(evidence, dict) or set(evidence) != {"method", "artifact_locator", "artifact_sha256", "notes"}:
            raise ReleaseError(f"quality review lacks immutable evidence: {logical_path}")
        if evidence.get("method") != "critical-listening" or not re.fullmatch(r"evidence/[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)*", str(evidence.get("artifact_locator", ""))) or not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("artifact_sha256", ""))) or not isinstance(evidence.get("notes"), str) or not evidence["notes"].strip():
            raise ReleaseError(f"quality review has invalid evidence: {logical_path}")
        verify_review_evidence(evidence, logical_path)
        reviews[logical_path] = entry
    return reviews


def codec_contract(suffix: str) -> tuple[str, str, str]:
    if suffix == ".mid":
        return "midi", "standard-midi-file", "timidity"
    if suffix in TRACKER_SUFFIXES:
        return suffix[1:], "tracker-module", "openmpt123"
    if suffix == ".ogg":
        return "vorbis", "ogg", "ffmpeg"
    raise ReleaseError(f"unsupported suffix: {suffix}")


def checked_license_reviews() -> dict[str, dict[str, object]]:
    checked_schema("license-reviews-v1.schema.json")
    value = read_json(LICENSE_REVIEWS)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "reviews"} or value.get("$schema") != "../schemas/license-reviews-v1.schema.json" or value.get("schema_version") != 1 or not isinstance(value.get("reviews"), list):
        raise ReleaseError("license-review ledger must use the complete version 1 contract")
    validate_schema_instance(value, checked_schema("license-reviews-v1.schema.json"))
    reviews: dict[str, dict[str, object]] = {}
    for review in value["reviews"]:
        assert isinstance(review, dict)
        logical = str(review["logical_path"])
        if logical in reviews:
            raise ReleaseError(f"duplicate license review: {logical}")
        reviewed_at = str(review["reviewed_at"])
        try:
            if datetime.strptime(reviewed_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != reviewed_at:
                raise ValueError
        except ValueError as exc:
            raise ReleaseError(f"license review has a non-canonical UTC timestamp: {logical}") from exc
        evidence = review["evidence"]
        assert isinstance(evidence, dict)
        verify_review_evidence(evidence, logical)
        reviews[logical] = review
    return reviews


def build_source_manifest() -> dict[str, object]:
    toolchain = checked_toolchain()
    budget = toolchain["quality_budget"]
    assert isinstance(budget, dict)
    sample_rate = int(budget["sample_rate"])
    catalogs = {
        "background": notice_catalog(ROOT / "background"),
        "effects": notice_catalog(ROOT / "effects"),
    }
    assets: list[dict[str, object]] = []
    quality_reviews = checked_quality_reviews()
    license_reviews = checked_license_reviews()
    for path in discover_sources():
        relative = path.relative_to(ROOT).as_posix()
        logical = PurePosixPath(relative)
        metadata = source_metadata(path)
        codec, container, renderer = codec_contract(path.suffix.lower())
        notice = catalogs[logical.parts[0]].get(logical.name)
        status, finding, expression, license_text_path = notice_status(notice)
        source_hash = sha256(path)
        notice_hash = hashlib.sha256(notice["description"].encode("utf-8")).hexdigest() if notice else None
        review = license_reviews.get(relative)
        if status == "candidate" and review is not None:
            expected = (source_hash, notice_hash, expression)
            actual = (review.get("source_sha256"), review.get("notice_sha256"), review.get("spdx_expression"))
            if actual != expected:
                raise ReleaseError(f"stale per-asset license review: {relative}")
            status, finding = "allowed", None
        elif status == "candidate":
            status = "blocked"
        generated = f"audio/{logical.parent}/{logical.name}.opus"
        channels = metadata.channels if metadata.channels is not None else 2
        bitrate = int(budget["mono_bitrate_kbps"] if channels == 1 else budget["stereo_music_bitrate_kbps"])
        render_recipes = {
            "timidity": ["timidity", "-c", "{instrument_config}", "-Ow", "-s", str(sample_rate), "-o", "{output}", "{input}"],
            "openmpt123": ["openmpt123", "--quiet", "--batch", "--samplerate", str(sample_rate), "--channels", "2", "--no-float", "--dither", "0", "--force", "--output", "{output}", "--", "{input}"],
            "ffmpeg": ["ffmpeg", "-nostdin", "-v", "error", "-i", "{input}", "-map_metadata", "-1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", "-y", "{output}"],
        }
        asset: dict[str, object] = {
            "id": f"sound:{relative}",
            "logical_path": relative,
            "source_path": relative,
            "generated_path": generated,
            "source": {
                "sha256": source_hash,
                "codec": codec,
                "container": container,
                "sample_rate": metadata.sample_rate,
                "channels": metadata.channels,
                "duration_seconds": metadata.duration_seconds,
            },
            "render": {
                "renderer": renderer,
                "recipe": render_recipes[renderer],
                "sample_rate": sample_rate,
                "channels": channels,
                "tail_policy": "preserve-decoder-eof",
                "loop": logical.parts[0] == "background",
            },
            "encode": {
                "codec": "opus",
                "container": "ogg",
                "bitrate_kbps": bitrate,
                "mode": str(budget["rate_control"]).lower(),
                "signal": "music" if logical.parts[0] == "background" else "auto",
                "complexity": int(budget["encoder_complexity"]),
                "serial": int(source_hash[0:8], 16),
                "discard_comments": True,
            },
            "transformation_notes": (
                "second lossy generation from the only preserved Vorbis source; quality review required"
                if path.suffix.lower() == ".ogg"
                else "rendered from the preserved authored source at release time"
            ),
            "license": {
                "status": status,
                "notice": notice["description"] if notice else None,
                "notice_sha256": notice_hash,
                "notice_reference": notice["reference"] if notice else None,
                "blocking_finding": finding,
                "spdx_expression": expression,
                "license_text_path": license_text_path,
            },
        }
        if path.suffix.lower() == ".ogg":
            quality_review = quality_reviews.get(relative)
            if quality_review is not None and quality_review.get("source_sha256") != asset["source"]["sha256"]:  # type: ignore[index]
                raise ReleaseError(f"stale Vorbis quality review: {relative}")
            asset["quality_review"] = quality_review or {
                "status": "blocked",
                "blocking_finding": "second-generation Vorbis-to-Opus review evidence is missing",
                "source_sha256": asset["source"]["sha256"],  # type: ignore[index]
            }
        else:
            asset["quality_review"] = {"status": "not-required"}
        assets.append(asset)
    unused_reviews = set(quality_reviews) - {str(asset["logical_path"]) for asset in assets}
    if unused_reviews:
        raise ReleaseError(f"quality reviews reference unknown sources: {', '.join(sorted(unused_reviews))}")
    unused_license_reviews = set(license_reviews) - {str(asset["logical_path"]) for asset in assets}
    if unused_license_reviews:
        raise ReleaseError(f"license reviews reference unknown sources: {', '.join(sorted(unused_license_reviews))}")
    corpus_contract = [
        {"source_path": asset["source_path"], "sha256": asset["source"]["sha256"]}  # type: ignore[index]
        for asset in assets
    ]
    return {
        "$schema": "../schemas/source-assets-v1.schema.json",
        "schema_version": 1,
        "source_corpus_sha256": hashlib.sha256(canonical_json(corpus_contract)).hexdigest(),
        "audio_source_count": len(assets),
        "source_size_bytes": sum((ROOT / str(asset["source_path"])).stat().st_size for asset in assets),
        "assets": assets,
    }


def validate_manifest(
    manifest: dict[str, object], *, compare_generated: bool = True, verify_tracked: bool = False
) -> list[dict[str, object]]:
    schema = checked_schema("source-assets-v1.schema.json")
    if set(manifest) != {"$schema", "schema_version", "source_corpus_sha256", "audio_source_count", "source_size_bytes", "assets"} or manifest.get("$schema") != "../schemas/source-assets-v1.schema.json" or manifest.get("schema_version") != 1:
        raise ReleaseError("source manifest does not satisfy the version 1 schema")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ReleaseError("source manifest assets must be an array")
    validate_schema_instance(manifest, schema)
    discovered = discover_sources()
    if verify_tracked:
        ensure_sources_tracked(discovered)
    if len(assets) != len(discovered):
        raise ReleaseError(f"source manifest has {len(assets)} assets; discovered {len(discovered)}")
    logical: set[str] = set()
    generated: set[str] = set()
    blockers: list[dict[str, object]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise ReleaseError("source manifest asset must be an object")
        if set(asset) != {"id", "logical_path", "source_path", "generated_path", "source", "render", "encode", "transformation_notes", "license", "quality_review"}:
            raise ReleaseError("source manifest asset has missing or unknown schema fields")
        source_contract = asset.get("source")
        render_contract = asset.get("render")
        encode_contract = asset.get("encode")
        if not isinstance(source_contract, dict) or set(source_contract) != {"sha256", "codec", "container", "sample_rate", "channels", "duration_seconds"}:
            raise ReleaseError("source metadata has missing or unknown schema fields")
        if not isinstance(render_contract, dict) or set(render_contract) != {"renderer", "recipe", "sample_rate", "channels", "tail_policy", "loop"}:
            raise ReleaseError("render contract has missing or unknown schema fields")
        if not isinstance(encode_contract, dict) or set(encode_contract) != {"codec", "container", "bitrate_kbps", "mode", "signal", "complexity", "serial", "discard_comments"}:
            raise ReleaseError("encode contract has missing or unknown schema fields")
        logical_path = asset.get("logical_path")
        generated_path = asset.get("generated_path")
        if not isinstance(logical_path, str) or logical_path in logical:
            raise ReleaseError(f"duplicate or invalid logical path: {logical_path!r}")
        if not isinstance(generated_path, str) or generated_path in generated:
            raise ReleaseError(f"duplicate or invalid generated path: {generated_path!r}")
        for label, candidate in (("logical", logical_path), ("generated", generated_path)):
            pure = PurePosixPath(candidate)
            if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != candidate:
                raise ReleaseError(f"unsafe {label} path: {candidate!r}")
        logical.add(logical_path)
        generated.add(generated_path)
        path = ROOT / logical_path
        if not path.is_file() or path.is_symlink():
            raise ReleaseError(f"manifest source is not a tracked regular file: {logical_path}")
        license_contract = asset.get("license")
        if not isinstance(license_contract, dict):
            raise ReleaseError(f"missing license contract: {logical_path}")
        if license_contract.get("status") == "blocked":
            blockers.append({
                "category": "license/provenance",
                "logical_path": logical_path,
                "generated_path": generated_path,
                "source_sha256": (
                    asset.get("source", {}).get("sha256")
                    if isinstance(asset.get("source"), dict)
                    else None
                ),
                "finding": license_contract.get("blocking_finding"),
                "notice": license_contract.get("notice"),
                "notice_reference": license_contract.get("notice_reference"),
            })
        elif license_contract.get("status") != "allowed":
            raise ReleaseError(f"invalid license status: {logical_path}")
        elif not license_contract.get("spdx_expression") or not license_contract.get("license_text_path"):
            raise ReleaseError(f"allowed notice lacks exact license material: {logical_path}")
        notice_reference = license_contract.get("notice_reference")
        if notice_reference is not None:
            match = re.fullmatch(r"(background/LICENSE|effects/LICENSE):([1-9][0-9]*)", str(notice_reference))
            if match is None:
                raise ReleaseError(f"invalid notice reference: {logical_path}")
            notice_lines = (ROOT / match.group(1)).read_text(encoding="utf-8").splitlines()
            line_number = int(match.group(2))
            if line_number > len(notice_lines) or PurePosixPath(logical_path).name not in notice_lines[line_number - 1]:
                raise ReleaseError(f"notice reference does not identify the asset: {logical_path}")
        quality_review = asset.get("quality_review")
        if not isinstance(quality_review, dict):
            raise ReleaseError(f"missing quality-review contract: {logical_path}")
        if quality_review.get("status") == "blocked":
            blockers.append({
                "category": "quality-review",
                "logical_path": logical_path,
                "generated_path": generated_path,
                "source_sha256": quality_review.get("source_sha256"),
                "finding": quality_review.get("blocking_finding"),
            })
        elif quality_review.get("status") not in {"passed", "not-required"}:
            raise ReleaseError(f"invalid quality-review status: {logical_path}")
    if compare_generated:
        expected = canonical_json(build_source_manifest())
        actual = canonical_json(manifest)
        if actual != expected:
            raise ReleaseError("source manifest is stale; run tools/sound_release.py refresh")
    return blockers


def checked_manifest() -> dict[str, object]:
    value = read_json(SOURCE_MANIFEST)
    if not isinstance(value, dict):
        raise ReleaseError("source manifest root must be an object")
    return value


def checked_toolchain() -> dict[str, object]:
    checked_schema("audio-toolchain-v1.schema.json")
    value = read_json(TOOLCHAIN)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "apt_snapshot", "build_image", "duration_tolerance_seconds", "quality_budget", "instrument_bank", "license_texts", "runtime_libraries", "tools"} or value.get("$schema") != "../schemas/audio-toolchain-v1.schema.json" or value.get("schema_version") != 1:
        raise ReleaseError("toolchain root must use schema version 1")
    validate_schema_instance(value, checked_schema("audio-toolchain-v1.schema.json"))
    if not re.fullmatch(r"https://snapshot\.ubuntu\.com/ubuntu/[0-9]{8}T[0-9]{6}Z", str(value.get("apt_snapshot", ""))):
        raise ReleaseError("toolchain must pin an immutable Ubuntu package snapshot")
    build_image = value.get("build_image")
    if not isinstance(build_image, dict) or set(build_image) != {"image", "source_repository", "source_commit", "release", "platform"}:
        raise ReleaseError("build-image contract is incomplete")
    if not re.fullmatch(r"ghcr\.io/atrinik/linux-build@sha256:[0-9a-f]{64}", str(build_image.get("image", ""))) or build_image.get("source_repository") != "atrinik/devcontainer" or not re.fullmatch(r"[0-9a-f]{40}", str(build_image.get("source_commit", ""))) or build_image.get("platform") != "linux/amd64":
        raise ReleaseError("build-image coordinates are invalid")
    budget = value.get("quality_budget")
    expected_budget = {
        "sample_rate": 48000,
        "sample_format": "signed 16-bit PCM intermediate",
        "stereo_music_bitrate_kbps": 160,
        "mono_bitrate_kbps": 80,
        "rate_control": "VBR",
        "encoder_complexity": 10,
        "clipping_allowed": False,
        "clipped_render_peak_target_dbfs": -2.0,
        "clipped_render_policy": "deterministically attenuate only full-scale rendered PCM before encoding",
        "nonzero_pcm_required": True,
        "vorbis_generation": "second lossy generation; each output requires quality review",
    }
    if budget != expected_budget:
        raise ReleaseError("quality-budget contract drifted from the validated deterministic recipe")
    if not isinstance(value.get("duration_tolerance_seconds"), (int, float)) or not 0 < float(value["duration_tolerance_seconds"]) <= 5:
        raise ReleaseError("duration tolerance must be a positive bounded number")
    required = {"ffmpeg", "timidity", "openmpt123", "opusenc", "opusinfo", "sdl3_mixer_probe"}
    tools = value.get("tools")
    if not isinstance(tools, dict) or set(tools) != required:
        raise ReleaseError(f"toolchain must define exactly: {', '.join(sorted(required))}")
    bank = value.get("instrument_bank")
    if not isinstance(bank, dict) or not bank.get("recording_distribution_permission"):
        raise ReleaseError("instrument bank must record permission to distribute rendered recordings")
    for key in ("name", "version", "installed_config", "installed_tree", "license", "license_reference", "transformation_note"):
        if not isinstance(bank.get(key), str) or not bank[key]:
            raise ReleaseError(f"instrument bank lacks {key}")
    for key in ("installed_config_sha256", "installed_tree_sha256", "upstream_archive_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(bank.get(key, ""))):
            raise ReleaseError(f"instrument bank lacks {key}")
    debian_source = bank.get("debian_source")
    if not isinstance(debian_source, dict) or set(debian_source) != {"url", "sha256"} or not str(debian_source.get("url", "")).startswith("https://") or not re.fullmatch(r"[0-9a-f]{64}", str(debian_source.get("sha256", ""))):
        raise ReleaseError("instrument-bank source contract is invalid")
    license_texts = value.get("license_texts")
    required_licenses = set(REVIEWED_NOTICE_LICENSES.values())
    required_expressions = {expression for expression, _path in required_licenses}
    if not isinstance(license_texts, dict) or set(license_texts) != required_expressions:
        raise ReleaseError("toolchain license texts do not cover every reviewed notice license")
    for expression, contract in license_texts.items():
        if not isinstance(contract, dict):
            raise ReleaseError(f"invalid license-text contract: {expression}")
        expected_path = next(path for license, path in required_licenses if license == expression)
        if contract.get("archive_path") != expected_path:
            raise ReleaseError(f"license archive path drift: {expression}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(contract.get("sha256", ""))):
            raise ReleaseError(f"license text lacks SHA-256: {expression}")
        if set(contract) != {"installed_path", "archive_path", "source_url", "sha256"} or not str(contract.get("source_url", "")).startswith("https://"):
            raise ReleaseError(f"license-text coordinates are incomplete: {expression}")
    libraries = value.get("runtime_libraries")
    if not isinstance(libraries, list) or not libraries:
        raise ReleaseError("toolchain runtime libraries must be a nonempty array")
    for library in libraries:
        if not isinstance(library, dict) or set(library) != {"path", "sha256"} or not str(library.get("path", "")).startswith("/") or not re.fullmatch(r"[0-9a-f]{64}", str(library.get("sha256", ""))):
            raise ReleaseError("runtime-library coordinates are invalid")
    for name, contract in tools.items():
        if not isinstance(contract, dict) or not isinstance(contract.get("purpose"), str):
            raise ReleaseError(f"invalid tool contract: {name}")
        if not isinstance(contract.get("version_command"), list) or not all(isinstance(part, str) and part for part in contract["version_command"]) or not isinstance(contract.get("version_pattern"), str):
            raise ReleaseError(f"tool version contract is invalid: {name}")
        if name != "sdl3_mixer_probe":
            if not re.fullmatch(r"[^=]+=.+", str(contract.get("package", ""))) or not str(contract.get("installed_path", "")).startswith("/") or not re.fullmatch(r"[0-9a-f]{64}", str(contract.get("installed_sha256", ""))):
                raise ReleaseError(f"tool package/install contract is invalid: {name}")
            upstream = contract.get("upstream")
            if not isinstance(upstream, dict) or set(upstream) != {"version", "url", "sha256"} or not str(upstream.get("url", "")).startswith("https://") or not re.fullmatch(r"[0-9a-f]{64}", str(upstream.get("sha256", ""))):
                raise ReleaseError(f"tool upstream contract is invalid: {name}")
    probe = tools["sdl3_mixer_probe"]
    assert isinstance(probe, dict)
    probe_source = probe.get("source_path")
    probe_sha256 = probe.get("source_sha256")
    if not isinstance(probe_source, str) or not isinstance(probe_sha256, str):
        raise ReleaseError("SDL3_mixer probe must pin its source path and SHA-256")
    probe_path = ROOT / probe_source
    if not probe_path.is_file() or sha256(probe_path) != probe_sha256:
        raise ReleaseError("SDL3_mixer probe source does not match its pinned SHA-256")
    dockerfile = (ROOT / "tools" / "audio" / "Dockerfile").read_text(encoding="utf-8")
    required_literals = [
        str(build_image["image"]),
        str(value["apt_snapshot"]),
        str(debian_source["url"]), str(debian_source["sha256"]), str(bank["upstream_archive_sha256"]),
        *(str(contract[field]) for contract in license_texts.values() if str(contract["installed_path"]).startswith("/opt/") for field in ("source_url", "sha256")),
        *(str(contract["package"]).split("=", 1)[1] for name, contract in tools.items() if name in {"ffmpeg", "openmpt123", "opusenc"}),
    ]
    if any(literal not in dockerfile for literal in required_literals):
        raise ReleaseError("Dockerfile drifts from pinned toolchain coordinates")
    return value


def checked_fixture_plan(manifest: dict[str, object]) -> dict[str, object]:
    schema = checked_schema("fixture-plan-v1.schema.json")
    value = read_json(FIXTURE_PLAN)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "consumer_boundary", "fixtures"} or value.get("$schema") != "../schemas/fixture-plan-v1.schema.json" or value.get("schema_version") != 1 or not isinstance(value.get("fixtures"), list):
        raise ReleaseError("fixture plan must contain a fixtures array")
    validate_schema_instance(value, schema)
    fixtures = value["fixtures"]
    planned = {fixture.get("logical_path") for fixture in fixtures if isinstance(fixture, dict)}
    if planned != set(FIXTURE_PATHS) or len(fixtures) != len(FIXTURE_PATHS):
        raise ReleaseError("fixture plan must cover each pinned fixture exactly once")
    assets = manifest.get("assets")
    assert isinstance(assets, list)
    known = {asset["logical_path"]: asset for asset in assets if isinstance(asset, dict)}
    represented: set[str] = set()
    allowed = {"loop", "seek", "stop", "mono", "stereo", "short-effect"}
    for fixture in fixtures:
        assert isinstance(fixture, dict)
        logical = fixture["logical_path"]
        if logical not in known:
            raise ReleaseError(f"fixture plan references a missing source: {logical}")
        behaviors = fixture.get("behaviors")
        if not isinstance(behaviors, list) or not behaviors or not all(isinstance(item, str) for item in behaviors) or len(behaviors) != len(set(behaviors)) or not set(behaviors) <= allowed:
            raise ReleaseError(f"fixture behaviors must be strings: {logical}")
        asset = known[logical]
        render = asset.get("render")
        source = asset.get("source")
        assert isinstance(render, dict) and isinstance(source, dict)
        expected_channel_behavior = "mono" if render.get("channels") == 1 else "stereo"
        if (set(behaviors) & {"mono", "stereo"}) != {expected_channel_behavior}:
            raise ReleaseError(f"fixture channel behavior disagrees with metadata: {logical}")
        if "short-effect" in behaviors:
            if not str(logical).startswith("effects/") or not isinstance(source.get("duration_seconds"), (int, float)) or not 0 < float(source["duration_seconds"]) <= 10:
                raise ReleaseError(f"short-effect fixture is not a measured short effect: {logical}")
        if "loop" in behaviors and not render.get("loop"):
            raise ReleaseError(f"loop fixture is not a looping asset: {logical}")
        represented.update(behaviors)
    required = {"loop", "seek", "stop", "mono", "stereo", "short-effect"}
    if not required <= represented:
        raise ReleaseError(f"fixture plan is missing behaviors: {', '.join(sorted(required - represented))}")
    return value


def validate_runtime_manifest(manifest: dict[str, object]) -> None:
    schema = checked_schema("runtime-manifest-v1.schema.json")
    required = {"$schema", "schema_version", "release_tag", "source_commit", "source_tree", "fixture_only", "source_size_bytes", "runtime_size_bytes", "quality_budget", "tool_versions", "toolchain_sha256", "assets"}
    if set(manifest) != required or manifest.get("$schema") != "schemas/runtime-manifest-v1.schema.json" or manifest.get("schema_version") != 1:
        raise ReleaseError("runtime manifest does not satisfy the version 1 schema")
    validate_schema_instance(manifest, schema)
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", str(manifest.get("release_tag", ""))) or not isinstance(manifest.get("fixture_only"), bool):
        raise ReleaseError("runtime manifest has invalid release coordinates")
    for key in ("source_commit", "source_tree"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get(key, ""))):
            raise ReleaseError(f"runtime manifest has invalid {key}")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ReleaseError("runtime manifest must contain assets")
    for asset in assets:
        if not isinstance(asset, dict) or "output" not in asset:
            raise ReleaseError("runtime manifest asset lacks output metadata")
        output = asset["output"]
        expected_output = {"sha256", "size_bytes", "codec", "container", "channels", "sample_rate", "duration_seconds", "peak", "rms_dbfs", "clipping", "rendered_pcm"}
        if not isinstance(output, dict) or set(output) != expected_output or output.get("codec") != "opus" or output.get("container") != "ogg" or output.get("clipping") is not False or not re.fullmatch(r"[0-9a-f]{64}", str(output.get("sha256", ""))):
            raise ReleaseError("runtime output metadata violates the version 1 schema")


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        rendered = " ".join(command)
        detail = getattr(exc, "stderr", None) or str(exc)
        raise ReleaseError(f"command failed: {rendered}: {detail.strip()}") from exc


def git_metadata_available() -> bool:
    try:
        return run(["git", "rev-parse", "--is-inside-work-tree"], capture=True).stdout.strip() == "true"
    except ReleaseError:
        return False


def source_revision(name: str, git_expression: str) -> str:
    value = os.environ.get(name)
    try:
        git_value = run(["git", "rev-parse", git_expression], capture=True).stdout.strip()
    except ReleaseError:
        git_value = None
    if value is None:
        value = git_value
    elif git_value is not None and value != git_value:
        raise ReleaseError(f"{name} does not match {git_expression}")
    if value is None:
        raise ReleaseError(f"{name} is required when Git metadata is unavailable")
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ReleaseError(f"{name} must be a full lowercase Git object ID")
    return value


def verify_release_tag(tag: str, source_commit: str, source_tree: str) -> None:
    try:
        tag_commit = run(["git", "rev-parse", f"{tag}^{{commit}}"], capture=True).stdout.strip()
        tag_tree = run(["git", "rev-parse", f"{tag}^{{tree}}"], capture=True).stdout.strip()
    except ReleaseError as exc:
        if os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") != "1" or git_metadata_available():
            raise ReleaseError("release tag cannot be verified without Git metadata") from exc
        tag_commit, tag_tree = source_commit, source_tree
    if (source_commit, source_tree) != (tag_commit, tag_tree):
        raise ReleaseError("runtime source commit/tree do not match the release tag")


def verify_toolchain(toolchain: dict[str, object]) -> dict[str, str]:
    versions: dict[str, str] = {}
    tools = toolchain["tools"]
    assert isinstance(tools, dict)
    for name, contract in tools.items():
        if not isinstance(contract, dict):
            raise ReleaseError(f"invalid tool contract: {name}")
        command = contract.get("version_command")
        expected = contract.get("version_pattern")
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ReleaseError(f"invalid version command: {name}")
        if not isinstance(expected, str):
            raise ReleaseError(f"invalid version pattern: {name}")
        executable = shutil.which(command[0])
        if executable is None:
            raise ReleaseError(f"required tool is missing: {command[0]}")
        completed = run(command, capture=True)
        output = (completed.stdout + completed.stderr).strip()
        if not re.search(expected, output, re.MULTILINE):
            raise ReleaseError(f"unexpected {name} version; expected /{expected}/, got: {output}")
        versions[name] = output.splitlines()[0]
        installed_path = contract.get("installed_path")
        installed_sha256 = contract.get("installed_sha256")
        if name != "sdl3_mixer_probe":
            if not isinstance(installed_path, str) or not isinstance(installed_sha256, str):
                raise ReleaseError(f"tool lacks an installed binary hash: {name}")
            installed = Path(installed_path)
            if not installed.is_file() or sha256(installed) != installed_sha256:
                raise ReleaseError(f"installed tool hash mismatch: {name}")
    libraries = toolchain.get("runtime_libraries")
    if not isinstance(libraries, list):
        raise ReleaseError("toolchain runtime libraries must be an array")
    for contract in libraries:
        if not isinstance(contract, dict):
            raise ReleaseError("invalid runtime-library contract")
        path = Path(str(contract.get("path", "")))
        if not path.is_file() or sha256(path) != contract.get("sha256"):
            raise ReleaseError(f"runtime library hash mismatch: {path}")
    bank = toolchain["instrument_bank"]
    assert isinstance(bank, dict)
    config = Path(str(bank["installed_config"]))
    tree = Path(str(bank["installed_tree"]))
    if not config.is_file() or sha256(config) != bank.get("installed_config_sha256"):
        raise ReleaseError("installed instrument-bank configuration hash mismatch")
    if not tree.is_dir() or installed_tree_sha256(tree) != bank.get("installed_tree_sha256"):
        raise ReleaseError("installed instrument-bank tree hash mismatch")
    license_texts = toolchain["license_texts"]
    assert isinstance(license_texts, dict)
    for expression, contract in license_texts.items():
        assert isinstance(contract, dict)
        installed = Path(str(contract["installed_path"]))
        if not installed.is_file() or sha256(installed) != contract["sha256"]:
            raise ReleaseError(f"installed license text hash mismatch: {expression}")
    return versions


def inspect_wave(path: Path) -> dict[str, object]:
    with contextlib.closing(wave.open(str(path), "rb")) as stream:
        channels = stream.getnchannels()
        sample_rate = stream.getframerate()
        width = stream.getsampwidth()
        frames = stream.getnframes()
        if width != 2:
            raise ReleaseError(f"expected 16-bit PCM WAV, got {width * 8}-bit: {path}")
        peak = 0
        square_sum = 0
        sample_count = 0
        while True:
            payload = stream.readframes(65536)
            if not payload:
                break
            samples = struct.unpack(f"<{len(payload) // 2}h", payload)
            peak = max(peak, *(abs(sample) for sample in samples))
            square_sum += sum(sample * sample for sample in samples)
            sample_count += len(samples)
    if sample_count == 0 or peak == 0:
        raise ReleaseError(f"decoded audio has zero PCM energy: {path}")
    rms = math.sqrt(square_sum / sample_count) / 32768
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": round(frames / sample_rate, 6),
        "peak": round(peak / 32768, 8),
        "rms_dbfs": round(20 * math.log10(rms), 4),
        "clipping": peak >= 32767,
    }


def attenuate_clipped_wave(path: Path, target_dbfs: float) -> dict[str, object]:
    before = inspect_wave(path)
    if not before["clipping"]:
        return {**before, "input_peak": before["peak"], "input_clipping": False, "applied_gain_db": 0.0}
    target_peak = int(32767 * (10 ** (target_dbfs / 20)))
    gain = target_peak / 32768
    replacement = path.with_suffix(".attenuated.wav")
    with contextlib.closing(wave.open(str(path), "rb")) as source:
        parameters = source.getparams()
        with contextlib.closing(wave.open(str(replacement), "wb")) as output:
            output.setparams(parameters)
            while True:
                payload = source.readframes(65536)
                if not payload:
                    break
                samples = struct.unpack(f"<{len(payload) // 2}h", payload)
                scaled = [max(-32767, min(32767, round(sample * gain))) for sample in samples]
                output.writeframesraw(struct.pack(f"<{len(scaled)}h", *scaled))
    replacement.replace(path)
    after = inspect_wave(path)
    if after["clipping"]:
        raise ReleaseError(f"peak attenuation did not remove clipping: {path}")
    return {
        **after,
        "input_peak": before["peak"],
        "input_clipping": True,
        "applied_gain_db": round(20 * math.log10(gain), 4),
    }


def render_source(asset: dict[str, object], output: Path, toolchain: dict[str, object]) -> None:
    source = ROOT / str(asset["source_path"])
    render = asset["render"]
    assert isinstance(render, dict)
    renderer = render["renderer"]
    recipe = render.get("recipe")
    if not isinstance(recipe, list) or not all(isinstance(part, str) for part in recipe):
        raise ReleaseError(f"invalid render recipe for {asset['logical_path']}")
    replacements = {"{input}": str(source), "{output}": str(output)}
    if renderer == "timidity":
        bank = toolchain["instrument_bank"]
        assert isinstance(bank, dict)
        config_path = Path(os.environ.get("ATRINIK_INSTRUMENT_CONFIG", str(bank["installed_config"])))
        if not config_path.is_file():
            raise ReleaseError(f"pinned instrument-bank config is missing: {config_path}")
        replacements["{instrument_config}"] = str(config_path)
    elif renderer not in {"openmpt123", "ffmpeg"}:
        raise ReleaseError(f"unknown renderer {renderer!r} for {asset['logical_path']}")
    command = recipe
    for placeholder, replacement in replacements.items():
        command = [part.replace(placeholder, replacement) for part in command]
    if any(re.fullmatch(r"\{[^}]+\}", part) for part in command):
        raise ReleaseError(f"unresolved render recipe placeholder for {asset['logical_path']}")
    run(command)


def encode_opus(asset: dict[str, object], wave_path: Path, opus_path: Path) -> None:
    encode = asset["encode"]
    assert isinstance(encode, dict)
    serial = int(str(asset["source"]["sha256"])[0:8], 16)  # type: ignore[index]
    command = [
        "opusenc",
        "--quiet",
        "--bitrate", str(encode["bitrate_kbps"]),
        f"--{encode['mode']}",
        "--comp", str(encode["complexity"]),
        "--serial", str(serial),
        "--discard-comments",
    ]
    if encode["signal"] == "music":
        command.append("--music")
    command.extend([str(wave_path), str(opus_path)])
    run(command)


def convert_asset(
    asset: dict[str, object],
    output_root: Path,
    toolchain: dict[str, object],
    behaviors: tuple[str, ...] = (),
) -> dict[str, object]:
    generated = output_root / str(asset["generated_path"])
    generated.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-") as temporary:
        temporary_path = Path(temporary)
        rendered_wave = temporary_path / "rendered.wav"
        decoded_wave = temporary_path / "decoded.wav"
        render_source(asset, rendered_wave, toolchain)
        quality_budget = toolchain["quality_budget"]
        assert isinstance(quality_budget, dict)
        rendered = attenuate_clipped_wave(
            rendered_wave,
            float(quality_budget["clipped_render_peak_target_dbfs"]),
        )
        encode_opus(asset, rendered_wave, generated)
        run(["opusinfo", "-q", str(generated)])
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(generated), "-map_metadata", "-1", "-c:a", "pcm_s16le", "-y", str(decoded_wave)])
        decoded = inspect_wave(decoded_wave)
        if decoded["clipping"]:
            raise ReleaseError(f"decoded Opus PCM clips for {asset['logical_path']}")
        probe = toolchain["tools"]["sdl3_mixer_probe"]  # type: ignore[index]
        assert isinstance(probe, dict)
        probe_command = probe["decode_command"]
        assert isinstance(probe_command, list)
        replacements = {
            "{input}": str(generated),
            "{expected_frames}": str(round(float(decoded["duration_seconds"]) * int(quality_budget["sample_rate"]))),
            "{behaviors}": ",".join(behaviors) or "none",
            "{expected_channels}": str(asset["render"]["channels"]),  # type: ignore[index]
        }
        command = [str(part) for part in probe_command]
        for placeholder, value in replacements.items():
            command = [part.replace(placeholder, value) for part in command]
        run(command)
    intended_channels = int(asset["render"]["channels"])  # type: ignore[index]
    expected_rate = int(toolchain["quality_budget"]["sample_rate"])  # type: ignore[index]
    if rendered["sample_rate"] != expected_rate or decoded["sample_rate"] != expected_rate:
        raise ReleaseError(f"unexpected output sample rate for {asset['logical_path']}")
    if rendered["channels"] != intended_channels or decoded["channels"] != intended_channels:
        raise ReleaseError(f"unexpected output channel count for {asset['logical_path']}")
    if abs(float(decoded["duration_seconds"]) - float(rendered["duration_seconds"])) > 0.1:
        raise ReleaseError(f"Opus output has a truncated or extended tail for {asset['logical_path']}")
    source_duration = float(asset["source"]["duration_seconds"])  # type: ignore[index]
    tolerance = float(toolchain["duration_tolerance_seconds"])
    if abs(float(decoded["duration_seconds"]) - source_duration) > tolerance:
        raise ReleaseError(
            f"duration outside {tolerance}s tolerance for {asset['logical_path']}: "
            f"source={source_duration}, decoded={decoded['duration_seconds']}"
        )
    output_sha256 = sha256(generated)
    quality_review = asset.get("quality_review")
    if isinstance(quality_review, dict) and quality_review.get("status") == "passed" and quality_review.get("output_sha256") != output_sha256:
        raise ReleaseError(f"Vorbis quality review output hash mismatch: {asset['logical_path']}")
    result = dict(asset)
    result["output"] = {
        "sha256": output_sha256,
        "size_bytes": generated.stat().st_size,
        "codec": "opus",
        "container": "ogg",
        **decoded,
        "rendered_pcm": rendered,
    }
    return result


def deterministic_archive(root: Path, output: Path, prefix: str, epoch: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.chmod(0o644)
        raw = temporary.open("wb")
        with raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch, compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
                        if not path.is_file() or path.is_symlink():
                            continue
                        relative = path.relative_to(root).as_posix()
                        payload = path.read_bytes()
                        info = tarfile.TarInfo(f"{prefix}/{relative}")
                        info.size = len(payload)
                        info.mtime = epoch
                        info.mode = 0o644
                        info.uid = 0
                        info.gid = 0
                        info.uname = "root"
                        info.gname = "root"
                        archive.addfile(info, io.BytesIO(payload))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def write_tree_checksums(root: Path) -> None:
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and not path.is_symlink()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    payload = "".join(
        f"{sha256(path)}  {path.relative_to(root).as_posix()}\n"
        for path in files
    ).encode("ascii")
    atomic_write(root / "SHA256SUMS", payload)


def build_runtime(tag: str, output_directory: Path, *, fixtures: bool) -> Path:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ReleaseError(f"invalid release tag: {tag}")
    manifest = checked_manifest()
    blockers = validate_manifest(manifest, verify_tracked=not fixtures)
    assets = manifest["assets"]
    assert isinstance(assets, list)
    if fixtures:
        fixture_plan = checked_fixture_plan(manifest)
        selected = [asset for asset in assets if asset["logical_path"] in FIXTURE_PATHS]
        missing = set(FIXTURE_PATHS) - {str(asset["logical_path"]) for asset in selected}
        if missing:
            raise ReleaseError(f"fixture sources are missing: {', '.join(sorted(missing))}")
    else:
        fixture_plan = {"fixtures": []}
        if blockers:
            raise ReleaseError(
                f"runtime release blocked by {len(blockers)} release findings; "
                "see manifests/source-assets.json"
            )
        ensure_clean_release_input()
        selected = assets
    toolchain = checked_toolchain()
    versions = verify_toolchain(toolchain)
    epoch_text = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch_text is None or not epoch_text.isdigit():
        raise ReleaseError("SOURCE_DATE_EPOCH must be a non-negative integer")
    epoch = int(epoch_text)
    source_commit = source_revision("ATRINIK_SOURCE_COMMIT", "HEAD")
    source_tree = source_revision("ATRINIK_SOURCE_TREE", "HEAD^{tree}")
    if not fixtures:
        verify_release_tag(tag, source_commit, source_tree)
    version = tag[1:]
    suffix = "fixture" if fixtures else "runtime"
    package = f"atrinik-sound-{suffix}-{version}"
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-runtime-") as temporary:
        staging = Path(temporary) / package
        staging.mkdir(parents=True)
        planned_behaviors = {
            str(fixture["logical_path"]): tuple(str(item) for item in fixture["behaviors"])
            for fixture in fixture_plan["fixtures"]  # type: ignore[index]
        }
        converted = [
            convert_asset(
                asset,
                staging,
                toolchain,
                planned_behaviors.get(str(asset["logical_path"]), ()),
            )
            for asset in selected
        ]
        runtime_manifest = {
            "$schema": "schemas/runtime-manifest-v1.schema.json",
            "schema_version": 1,
            "release_tag": tag,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "fixture_only": fixtures,
            "source_size_bytes": sum((ROOT / str(asset["source_path"])).stat().st_size for asset in selected),
            "runtime_size_bytes": sum((staging / str(asset["generated_path"])).stat().st_size for asset in converted),
            "quality_budget": toolchain["quality_budget"],
            "tool_versions": versions,
            "toolchain_sha256": sha256(TOOLCHAIN),
            "assets": converted,
        }
        validate_runtime_manifest(runtime_manifest)
        (staging / "manifest.json").write_bytes(canonical_json(runtime_manifest))
        schema_root = staging / "schemas"
        schema_root.mkdir()
        shutil.copyfile(SCHEMA_ROOT / "runtime-manifest-v1.schema.json", schema_root / "runtime-manifest-v1.schema.json")
        shutil.copyfile(SCHEMA_ROOT / "audio-toolchain-v1.schema.json", schema_root / "audio-toolchain-v1.schema.json")
        for notice_path in ("background/LICENSE", "effects/LICENSE"):
            destination = staging / notice_path
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / notice_path, destination)
        license_root = staging / "licenses"
        license_root.mkdir()
        license_texts = toolchain["license_texts"]
        assert isinstance(license_texts, dict)
        for contract in license_texts.values():
            assert isinstance(contract, dict)
            destination = staging / str(contract["archive_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(str(contract["installed_path"])), destination)
        shutil.copyfile(TOOLCHAIN, license_root / "audio-toolchain.json")
        write_tree_checksums(staging)
        output = output_directory / f"{package}.tar.gz"
        deterministic_archive(staging, output, package, epoch)
    return output


def write_checksums(output_directory: Path) -> None:
    assets = sorted(
        (
            path
            for path in output_directory.iterdir()
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        key=lambda path: path.name,
    )
    if not assets:
        raise ReleaseError(f"no archives found in {output_directory}")
    payload = "".join(f"{sha256(path)}  {path.name}\n" for path in assets)
    atomic_write(output_directory / "SHA256SUMS", payload.encode("ascii"))


def command_refresh(_arguments: argparse.Namespace) -> None:
    ensure_sources_tracked(discover_sources())
    manifest = build_source_manifest()
    atomic_write(SOURCE_MANIFEST, canonical_json(manifest))
    print(f"wrote {SOURCE_MANIFEST.relative_to(ROOT)} with {manifest['audio_source_count']} assets")


def command_measure_trackers(_arguments: argparse.Namespace) -> None:
    toolchain = checked_toolchain()
    verify_toolchain(toolchain)
    entries = [
        {
            "logical_path": path.relative_to(ROOT).as_posix(),
            "source_sha256": sha256(path),
            "duration_seconds": measured_tracker_duration(path),
        }
        for path in discover_sources()
        if path.suffix.lower() in TRACKER_SUFFIXES
    ]
    document = {
        "$schema": "../schemas/tracker-durations-v1.schema.json",
        "schema_version": 1,
        "toolchain_sha256": sha256(TOOLCHAIN),
        "entries": entries,
    }
    print(canonical_json(document).decode("utf-8"), end="")


def command_build_review_candidate(arguments: argparse.Namespace) -> None:
    manifest = checked_manifest()
    validate_manifest(manifest)
    assets = manifest["assets"]
    assert isinstance(assets, list)
    selected = [asset for asset in assets if isinstance(asset, dict) and asset.get("logical_path") == arguments.logical_path]
    if len(selected) != 1:
        raise ReleaseError(f"unknown review-candidate source: {arguments.logical_path}")
    asset = selected[0]
    license_contract = asset.get("license")
    if not isinstance(license_contract, dict) or license_contract.get("status") != "allowed":
        raise ReleaseError("review candidate requires a passed per-asset license review")
    output_directory = Path(arguments.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    if any(output_directory.iterdir()):
        raise ReleaseError(f"review-candidate output directory must be empty: {output_directory}")
    toolchain = checked_toolchain()
    versions = verify_toolchain(toolchain)
    converted = convert_asset(asset, output_directory, toolchain)
    output = converted["output"]
    assert isinstance(output, dict)
    evidence = {
        "schema_version": 1,
        "logical_path": asset["logical_path"],
        "source_sha256": asset["source"]["sha256"],  # type: ignore[index]
        "toolchain_sha256": sha256(TOOLCHAIN),
        "output_sha256": output["sha256"],
        "generated_path": asset["generated_path"],
        "tool_versions": versions,
        "measurements": output,
        "non_publishing": True,
    }
    atomic_write(output_directory / "review-evidence.json", canonical_json(evidence))
    print(output_directory / str(asset["generated_path"]))


def command_validate(_arguments: argparse.Namespace) -> None:
    manifest = checked_manifest()
    blockers = validate_manifest(manifest, verify_tracked=True)
    checked_toolchain()
    checked_fixture_plan(manifest)
    print(
        f"validated {manifest['audio_source_count']} sources; "
        f"runtime blockers: {len(blockers)}"
    )


def command_blockers(_arguments: argparse.Namespace) -> None:
    manifest = checked_manifest()
    blockers = validate_manifest(manifest)
    report = {
        "schema_version": 1,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "source_count": manifest["audio_source_count"],
        "count": len(blockers),
        "findings": blockers,
    }
    print(canonical_json(report).decode("utf-8"), end="")


def command_build(arguments: argparse.Namespace) -> None:
    output = build_runtime(arguments.tag, Path(arguments.output_directory), fixtures=arguments.fixtures)
    print(output)


def command_checksums(arguments: argparse.Namespace) -> None:
    write_checksums(Path(arguments.output_directory))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("refresh", help="regenerate the checked source manifest")
    refresh.set_defaults(function=command_refresh)
    trackers = commands.add_parser("measure-trackers", help="print tracker durations measured by the pinned toolchain")
    trackers.set_defaults(function=command_measure_trackers)
    validate = commands.add_parser("validate", help="validate source, notice, and toolchain contracts")
    validate.set_defaults(function=command_validate)
    blockers = commands.add_parser("blockers", help="print fail-closed runtime findings as JSON")
    blockers.set_defaults(function=command_blockers)
    build = commands.add_parser("build-runtime", help="build the full or fixture Opus archive")
    build.add_argument("tag")
    build.add_argument("output_directory")
    build.add_argument("--fixtures", action="store_true", help="build the six-format CI fixture archive")
    build.set_defaults(function=command_build)
    candidate = commands.add_parser("build-review-candidate", help="build one license-approved non-publishing quality-review candidate")
    candidate.add_argument("logical_path")
    candidate.add_argument("output_directory")
    candidate.set_defaults(function=command_build_review_candidate)
    checksums = commands.add_parser("checksums", help="write deterministic checksums for release archives")
    checksums.add_argument("output_directory")
    checksums.set_defaults(function=command_checksums)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        arguments.function(arguments)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
