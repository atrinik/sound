#!/usr/bin/env python3
"""Build and validate deterministic Atrinik sound release artifacts."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import filecmp
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
from datetime import UTC, datetime


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
    'Bernd Krueger - https://www.piano-midi.de/ - CC BY-SA 3.0 Germany': ("CC-BY-SA-3.0-DE", "licenses/CC-BY-SA-3.0-DE.txt"),
    'Edwin "Mamoru" Miltenburg - GPLv2': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'http://sites.google.com/site/metaruka/GameGame - CC BY-SA 3.0': ("CC-BY-SA-3.0", "licenses/CC-BY-SA-3.0.txt"),
    'Allacrost - http://allacrost.org/ - GPLv2': ("GPL-2.0-only", "licenses/GPL-2.0.txt"),
    'Ecrivain - http://opengameart.org/users/Ecrivain - CC0': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'Brandon Morris / HaelDB / Augmentality - OpenGameArt - CC0 1.0': ("CC0-1.0", "licenses/CC0-1.0.txt"),
    'Yo Frankie! - http://www.yofrankie.org/ - CC-BY 3.0': ("CC-BY-3.0", "licenses/CC-BY-3.0.txt"),
    'Gobusto - http://opengameart.org/users/gobusto - CC-BY-SA 3.0': ("CC-BY-SA-3.0", "licenses/CC-BY-SA-3.0.txt"),
    'Sylvain Beucler / GNU FreeDink - https://www.gnu.org/software/freedink/ - GPLv3+': ("GPL-3.0-or-later", "licenses/GPL-3.0.txt"),
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
    lines = license_path.read_bytes().decode("utf-8").splitlines(keepends=True)
    current = ""
    current_raw = ""
    notices: dict[str, dict[str, str]] = {}
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip("\r\n")
        if line and not line[0].isspace() and line.endswith(":"):
            current = line[:-1]
            current_raw = raw_line
            continue
        match = re.match(r"^\s{4}([A-Za-z0-9_.-]+\.(?:mid|mod|s3m|xm|ogg))\b", line)
        if match and current:
            filename = match.group(1)
            if filename in notices:
                raise ReleaseError(f"duplicate notice for {directory.name}/{filename}")
            notices[filename] = {
                "description": current,
                "reference": f"{directory.name}/LICENSE:{line_number}",
                "text": current_raw + raw_line,
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


def verify_review_artifact(artifact: dict[str, object], logical_path: str) -> None:
    locator = artifact.get("artifact_locator", artifact.get("locator"))
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
    if sha256(path) != artifact.get("artifact_sha256", artifact.get("sha256")):
        raise ReleaseError(f"review evidence hash mismatch: {logical_path}")


def verify_review_evidence(evidence: dict[str, object], logical_path: str) -> None:
    verify_review_artifact(evidence, logical_path)
    artifacts = evidence.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ReleaseError(f"review supporting artifacts are invalid: {logical_path}")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ReleaseError(f"review supporting artifact is invalid: {logical_path}")
        verify_review_artifact(artifact, logical_path)


def checked_critical_listening_result(path: Path) -> dict[str, object]:
    value = read_json(path)
    validate_schema_instance(value, checked_schema("critical-listening-review-v1.schema.json"))
    assert isinstance(value, dict)
    try:
        reviewed_at = datetime.strptime(str(value["reviewed_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ReleaseError("critical-listening result has a non-canonical review timestamp") from exc
    if reviewed_at > datetime.now(UTC):
        raise ReleaseError("critical-listening result has a future review timestamp")
    reviews = value["reviews"]
    assert isinstance(reviews, list)
    for review in reviews:
        assert isinstance(review, dict)
        for field in ("artifacts", "noise_floor", "duration_tail", "loop_boundary"):
            if len(str(review[field]).strip()) < 8:
                raise ReleaseError(f"critical-listening result lacks substantive {field} notes: {review['logical_path']}")
    return value


def quality_review_input_sha256(assets: list[dict[str, object]]) -> str:
    inputs = [
        {key: value for key, value in asset.items() if key != "quality_review"}
        for asset in sorted(assets, key=lambda item: str(item["logical_path"]))
    ]
    return hashlib.sha256(canonical_json(inputs)).hexdigest()


def review_snapshot_manifest(result: dict[str, object]) -> tuple[dict[str, object], bool]:
    source_tree = str(result.get("source_tree", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", source_tree):
        raise ReleaseError("critical-listening result lacks an immutable source tree")
    if git_metadata_available():
        completed = run([
            "git", "show", f"{source_tree}:manifests/source-assets.json",
        ], capture=True)
        try:
            snapshot = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ReleaseError("critical-listening source tree has an invalid source manifest") from exc
        if not isinstance(snapshot, dict):
            raise ReleaseError("critical-listening source tree has an invalid source manifest")
        return snapshot, True
    if os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") != "1":
        raise ReleaseError("critical-listening source tree requires Git metadata")
    return checked_manifest(), False


def quality_review_bundle_contract(
    result: dict[str, object],
) -> dict[str, object]:
    current_manifest = checked_manifest()
    assets = current_manifest.get("assets")
    assert isinstance(assets, list)
    current_by_path = {
        str(asset["logical_path"]): asset for asset in assets if isinstance(asset, dict)
    }
    reviews = result.get("reviews")
    assert isinstance(reviews, list)
    bundle_assets: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for review in reviews:
        assert isinstance(review, dict)
        logical_path = str(review["logical_path"])
        if logical_path in seen_paths:
            raise ReleaseError(f"duplicate critical-listening result: {logical_path}")
        seen_paths.add(logical_path)
        current = current_by_path.get(logical_path)
        candidate_evidence = review.get("candidate_evidence")
        if current is None or not isinstance(candidate_evidence, dict):
            raise ReleaseError(f"critical-listening result references an unknown asset: {logical_path}")
        source = current.get("source")
        license_contract = current.get("license")
        measurements = candidate_evidence.get("measurements")
        rendered_pcm = measurements.get("rendered_pcm") if isinstance(measurements, dict) else None
        candidate_gain = rendered_pcm.get("applied_gain_db") if isinstance(rendered_pcm, dict) else None
        invalid = (
            not isinstance(source, dict),
            not isinstance(license_contract, dict),
            not isinstance(rendered_pcm, dict),
            source.get("sha256") != review.get("source_sha256") if isinstance(source, dict) else True,
            license_contract.get("status") != "allowed" if isinstance(license_contract, dict) else True,
            candidate_evidence.get("logical_path") != logical_path,
            candidate_evidence.get("source_sha256") != review.get("source_sha256"),
            candidate_evidence.get("output_sha256") != review.get("output_sha256"),
            candidate_evidence.get("toolchain_sha256") != result.get("toolchain_sha256"),
            candidate_evidence.get("generated_path") != current.get("generated_path"),
            not isinstance(candidate_gain, (int, float)) or isinstance(candidate_gain, bool),
        )
        if any(invalid):
            raise ReleaseError(f"critical-listening result does not match the current asset: {logical_path}")
        candidate_root = PurePosixPath("candidates") / PurePosixPath(logical_path)
        expected_evidence_path = (candidate_root / "review-evidence.json").as_posix()
        if review.get("review_evidence_path") != expected_evidence_path:
            raise ReleaseError(f"critical-listening result has a stale evidence path: {logical_path}")
        bundle_assets.append({
            "logical_path": logical_path,
            "source_path": (PurePosixPath("sources") / PurePosixPath(logical_path)).as_posix(),
            "source_sha256": review["source_sha256"],
            "candidate_path": (candidate_root / str(current["generated_path"])).as_posix(),
            "output_sha256": review["output_sha256"],
            "candidate_gain_db": candidate_gain,
            "review_evidence_path": expected_evidence_path,
            "candidate_evidence": candidate_evidence,
        })
    asset_classes = {str(asset["logical_path"]).partition("/")[0] for asset in bundle_assets}
    if len(asset_classes) != 1 or not asset_classes <= {"background", "effects"}:
        raise ReleaseError("critical-listening result must contain exactly one asset class")
    asset_class = next(iter(asset_classes))
    snapshot_manifest, snapshot_verified = review_snapshot_manifest(result)
    expected_assets = eligible_vorbis_review_assets(snapshot_manifest, asset_class)
    if not snapshot_verified:
        expected_assets = [
            current_by_path[str(asset["logical_path"])]
            for asset in bundle_assets
        ]
    expected_paths = {str(asset["logical_path"]) for asset in expected_assets}
    if {str(asset["logical_path"]) for asset in bundle_assets} != expected_paths:
        raise ReleaseError("critical-listening result does not cover the exact eligible asset set")
    review_input_sha256 = quality_review_input_sha256(expected_assets)
    if result.get("review_input_sha256") != review_input_sha256:
        raise ReleaseError("critical-listening result has a stale review-input contract")
    bundle: dict[str, object] = {
        "schema_version": 1,
        "non_publishing": True,
        "source_tree": result["source_tree"],
        "review_input_sha256": review_input_sha256,
        "toolchain_sha256": result["toolchain_sha256"],
        "assets": sorted(bundle_assets, key=lambda item: str(item["logical_path"])),
    }
    canonical_core = json.loads(canonical_json(bundle))
    assert isinstance(canonical_core, dict)
    bundle = canonical_core
    bundle["contract_sha256"] = hashlib.sha256(canonical_json(bundle)).hexdigest()
    bundle["worksheet_contract_sha256"] = worksheet_contract_sha256(bundle)
    bundle["worksheet_sha256"] = hashlib.sha256(review_bundle_html(bundle)).hexdigest()
    if bundle["contract_sha256"] != result.get("review_bundle_sha256"):
        raise ReleaseError("critical-listening result does not bind its canonical review bundle")
    if bundle["worksheet_contract_sha256"] != result.get("worksheet_contract_sha256"):
        raise ReleaseError("critical-listening result does not bind its canonical worksheet")
    return bundle


def verify_quality_review_source_tree(result: dict[str, object], artifact_locator: str) -> None:
    if not git_metadata_available():
        if os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") == "1":
            return
        raise ReleaseError("quality-review source-tree binding requires Git metadata")
    introductions = run([
        "git", "log", "--follow", "--diff-filter=A", "--format=%H", "--", artifact_locator,
    ], capture=True).stdout.splitlines()
    if len(introductions) != 1:
        raise ReleaseError("quality-review evidence lacks one Git introduction commit")
    parents = run([
        "git", "show", "-s", "--format=%P", introductions[0],
    ], capture=True).stdout.split()
    if len(parents) != 1:
        raise ReleaseError("quality-review evidence introduction must have one parent")
    parent_tree = run([
        "git", "rev-parse", f"{parents[0]}^{{tree}}",
    ], capture=True).stdout.strip()
    if parent_tree != result.get("source_tree"):
        raise ReleaseError("quality-review evidence was not introduced over its source tree")


def verify_quality_review_result(
    entry: dict[str, object],
    evidence: dict[str, object],
    logical_path: str,
) -> None:
    result = checked_critical_listening_result(ROOT / str(evidence["artifact_locator"]))
    quality_review_bundle_contract(result)
    verify_quality_review_source_tree(result, str(evidence["artifact_locator"]))
    reviews = result["reviews"]
    assert isinstance(reviews, list)
    matches = [review for review in reviews if isinstance(review, dict) and review.get("logical_path") == logical_path]
    if len(matches) != 1:
        raise ReleaseError(f"quality-review artifact lacks one exact result: {logical_path}")
    review = matches[0]
    candidate_evidence = review.get("candidate_evidence")
    if not isinstance(candidate_evidence, dict) or any((
        review.get("verdict") != "passed",
        result.get("reviewed_by") != entry.get("reviewed_by"),
        result.get("reviewed_at") != entry.get("reviewed_at"),
        result.get("toolchain_sha256") != entry.get("toolchain_sha256"),
        review.get("source_sha256") != entry.get("source_sha256"),
        review.get("output_sha256") != entry.get("output_sha256"),
        candidate_evidence.get("logical_path") != logical_path,
        candidate_evidence.get("source_sha256") != entry.get("source_sha256"),
        candidate_evidence.get("output_sha256") != entry.get("output_sha256"),
        candidate_evidence.get("toolchain_sha256") != entry.get("toolchain_sha256"),
    )):
        raise ReleaseError(f"quality-review ledger does not match passed artifact: {logical_path}")


def checked_quality_reviews() -> dict[str, dict[str, object]]:
    schema = checked_schema("vorbis-quality-reviews-v2.schema.json")
    value = read_json(QUALITY_REVIEWS)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "reviews"} or value.get("$schema") != "../schemas/vorbis-quality-reviews-v2.schema.json" or value.get("schema_version") != 2:
        raise ReleaseError("Vorbis quality-review root must use schema version 2")
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
        if not re.fullmatch(r"(?!.*--)[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", str(entry.get("reviewed_by", ""))):
            raise ReleaseError(f"quality review lacks a GitHub reviewer identity: {logical_path}")
        reviewed_at = entry.get("reviewed_at")
        try:
            if not isinstance(reviewed_at, str) or datetime.strptime(reviewed_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != reviewed_at:
                raise ValueError
        except ValueError as exc:
            raise ReleaseError(f"quality review has a non-canonical UTC timestamp: {logical_path}") from exc
        evidence = entry.get("evidence")
        if not isinstance(evidence, dict) or set(evidence) != {"method", "artifact_locator", "artifact_sha256", "github_attestation_url", "notes"}:
            raise ReleaseError(f"quality review lacks immutable evidence: {logical_path}")
        if evidence.get("method") != "critical-listening" or not re.fullmatch(r"evidence/[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)*", str(evidence.get("artifact_locator", ""))) or not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("artifact_sha256", ""))) or not re.fullmatch(r"https://github\.com/atrinik/sound/issues/(21|22)#issuecomment-[1-9][0-9]*", str(evidence.get("github_attestation_url", ""))) or not isinstance(evidence.get("notes"), str) or not evidence["notes"].strip():
            raise ReleaseError(f"quality review has invalid evidence: {logical_path}")
        verify_review_evidence(evidence, logical_path)
        reviews[logical_path] = entry
    for logical_path, entry in reviews.items():
        evidence = entry["evidence"]
        assert isinstance(evidence, dict)
        verify_quality_review_result(entry, evidence, logical_path)
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
    checked_schema("license-reviews-v2.schema.json")
    value = read_json(LICENSE_REVIEWS)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "reviews"} or value.get("$schema") != "../schemas/license-reviews-v2.schema.json" or value.get("schema_version") != 2 or not isinstance(value.get("reviews"), list):
        raise ReleaseError("license-review ledger must use the complete version 2 contract")
    validate_schema_instance(value, checked_schema("license-reviews-v2.schema.json"))
    reviews: dict[str, dict[str, object]] = {}
    for review in value["reviews"]:
        assert isinstance(review, dict)
        logical = str(review["logical_path"])
        if logical in reviews:
            raise ReleaseError(f"duplicate license review: {logical}")
        reviewed_at = str(review["reviewed_at"])
        try:
            parsed_reviewed_at = datetime.strptime(reviewed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if parsed_reviewed_at.strftime("%Y-%m-%dT%H:%M:%SZ") != reviewed_at:
                raise ValueError
        except ValueError as exc:
            raise ReleaseError(f"license review has a non-canonical UTC timestamp: {logical}") from exc
        if parsed_reviewed_at > datetime.now(UTC):
            raise ReleaseError(f"license review has a future timestamp: {logical}")
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
        notice_hash = hashlib.sha256(notice["text"].encode("utf-8")).hexdigest() if notice else None
        review = license_reviews.get(relative)
        if status == "candidate" and review is not None:
            expected = (source_hash, notice_hash, expression)
            actual = (review.get("source_sha256"), review.get("notice_sha256"), review.get("spdx_expression"))
            if actual != expected:
                raise ReleaseError(f"stale per-asset license review: {relative}")
            status, finding = "allowed", None
        elif status == "candidate":
            status = "blocked"
        elif review is not None:
            raise ReleaseError(f"license review does not apply to a reviewed notice: {relative}")
        review_hash = hashlib.sha256(canonical_json(review)).hexdigest() if status == "allowed" else None
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
            ) + (f"; license review SHA-256: {review_hash}" if review_hash is not None else ""),
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
        "clipped_render_policy": "deterministically attenuate rendered PCM above the peak target before encoding",
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
    target_peak = int(32767 * (10 ** (target_dbfs / 20))) / 32768
    if float(before["peak"]) <= target_peak:
        return {**before, "input_peak": before["peak"], "input_clipping": False, "applied_gain_db": 0.0}
    gain = target_peak / float(before["peak"])
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
        "input_clipping": before["clipping"],
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
    if not fixtures and (os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") != "1" or git_metadata_available()):
        verify_quality_review_attestations(checked_quality_reviews())
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


def write_review_candidate(
    asset: dict[str, object],
    output_directory: Path,
    toolchain: dict[str, object],
    versions: dict[str, str],
) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    if any(output_directory.iterdir()):
        raise ReleaseError(f"review-candidate output directory must be empty: {output_directory}")
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
    return evidence


def eligible_vorbis_review_assets(
    manifest: dict[str, object],
    asset_class: str | None = None,
) -> list[dict[str, object]]:
    assets = manifest["assets"]
    assert isinstance(assets, list)
    return sorted([
        asset for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("source"), dict)
        and asset["source"].get("codec") == "vorbis"  # type: ignore[union-attr]
        and isinstance(asset.get("license"), dict)
        and asset["license"].get("status") == "allowed"  # type: ignore[union-attr]
        and isinstance(asset.get("quality_review"), dict)
        and asset["quality_review"].get("status") == "blocked"  # type: ignore[union-attr]
        and (asset_class is None or str(asset["logical_path"]).startswith(f"{asset_class}/"))
    ], key=lambda item: str(item["logical_path"]))


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
    toolchain = checked_toolchain()
    evidence = write_review_candidate(asset, output_directory, toolchain, verify_toolchain(toolchain))
    print(output_directory / str(asset["generated_path"]))


WORKSHEET_CONTRACT_PLACEHOLDER = "ATRINIK_WORKSHEET_CONTRACT_SHA256_PLACEHOLDER"


def review_bundle_html_template(bundle: dict[str, object]) -> bytes:
    assets_json = json.dumps(bundle["assets"], ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Atrinik critical-listening review</title>
<style>
body{{font:16px/1.45 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#18202a;background:#f5f7fa}}
h1,h2{{line-height:1.2}} .notice,.asset{{background:white;border:1px solid #ccd4df;border-radius:8px;padding:1rem;margin:1rem 0}}
.transport{{display:flex;flex-wrap:wrap;align-items:center;gap:.6rem;margin:.75rem 0}} .transport button[aria-pressed="true"]{{outline:3px solid #2764c4}}
.transport input[type="range"]{{flex:1;min-width:12rem}} .transport input[type="checkbox"],.procedure input{{width:auto}} audio{{display:none}} label{{display:block;font-weight:650;margin-top:.75rem}}
textarea,input,select{{box-sizing:border-box;width:100%;font:inherit;padding:.5rem}} textarea{{min-height:4.5rem}} button{{font:inherit;padding:.65rem 1rem}}
code{{overflow-wrap:anywhere}} .hash,.gain{{font-size:.82rem}}
</style></head><body>
<h1>Atrinik critical-listening review</h1>
<div class="notice"><p>This is a non-publishing review aid. Use headphones and representative speakers. Listen to each complete source and candidate at normal and revealing levels, then compare loop boundaries. Do not pass a track with audible codec artifacts, tonal or transient changes, noise-floor modulation, truncation, tail loss, or a loop discontinuity.</p>
<label>GitHub reviewer identity <input id="reviewer" autocomplete="username" placeholder="username" pattern="(?!.*--)[A-Za-z0-9](?:[A-Za-z0-9-]{{0,37}}[A-Za-z0-9])?"></label>
<fieldset class="procedure"><legend>Required procedure attestations</legend>
<label><input type="checkbox" id="headphones"> I reviewed every pair on headphones.</label>
<label><input type="checkbox" id="speakers"> I reviewed every pair on representative speakers.</label>
<label><input type="checkbox" id="loops"> I compared every loop boundary.</label></fieldset></div>
<main id="assets"></main><button id="export">Export completed review JSON</button>
<script>const assets={assets_json};const root=document.querySelector('#assets');let playingAudio=null;
for(const a of assets){{const s=document.createElement('section');s.className='asset';s.dataset.logical=a.logical_path;s.dataset.sourceComplete='false';s.dataset.candidateComplete='false';
const h=document.createElement('h2');h.textContent=a.logical_path;s.append(h);
const hashes=document.createElement('p');hashes.className='hash';hashes.innerHTML='<code>'+a.source_sha256+'</code> → <code>'+a.output_sha256+'</code>';s.append(hashes);
const gain=document.createElement('p');gain.className='gain';gain.textContent='Candidate gain: '+a.candidate_gain_db.toFixed(4)+' dB. Source playback is level-matched by the same amount for unbiased A/B comparison.';s.append(gain);
const source=document.createElement('audio');source.preload='auto';source.src=a.source_path;source.volume=Math.pow(10,a.candidate_gain_db/20);
const candidate=document.createElement('audio');candidate.preload='auto';candidate.src=a.candidate_path;
const transport=document.createElement('div');transport.className='transport';
const play=document.createElement('button');play.type='button';play.textContent='Play';
const sourceButton=document.createElement('button');sourceButton.type='button';sourceButton.textContent='A: source';sourceButton.setAttribute('aria-pressed','true');
const candidateButton=document.createElement('button');candidateButton.type='button';candidateButton.textContent='B: candidate';candidateButton.setAttribute('aria-pressed','false');
const seek=document.createElement('input');seek.type='range';seek.min='0';seek.max='1000';seek.value='0';seek.setAttribute('aria-label','Playback position');
const loopLabel=document.createElement('label');loopLabel.textContent=' Loop';loopLabel.style.margin='0';const loop=document.createElement('input');loop.type='checkbox';loopLabel.prepend(loop);
const time=document.createElement('span');time.textContent='0:00';transport.append(play,sourceButton,candidateButton,seek,loopLabel,time);s.append(source,candidate,transport);const playback=document.createElement('p');playback.textContent='Complete playback: source pending; candidate pending';s.append(playback);
let active=source;const other=()=>active===source?candidate:source;const sync=()=>{{if(Number.isFinite(active.duration)&&active.duration>0){{seek.value=String(Math.round(1000*active.currentTime/active.duration));time.textContent=Math.floor(active.currentTime/60)+':'+String(Math.floor(active.currentTime%60)).padStart(2,'0')}}}};
const switchTo=next=>{{if(next===active)return;const wasPlaying=!active.paused;const at=active.currentTime;active.pause();active=next;active.currentTime=Math.min(at,Number.isFinite(active.duration)?active.duration:at);sourceButton.setAttribute('aria-pressed',String(active===source));candidateButton.setAttribute('aria-pressed',String(active===candidate));if(wasPlaying)active.play()}};
const completePlayback=audio=>{{if(!Number.isFinite(audio.duration)||audio.duration<=0)return false;let coveredUntil=0;for(let i=0;i<audio.played.length;i++){{const start=audio.played.start(i),end=audio.played.end(i);if(start>coveredUntil+0.25)return false;coveredUntil=Math.max(coveredUntil,end)}}return coveredUntil>=audio.duration-0.25}};
play.onclick=()=>{{if(active.paused)active.play();else active.pause()}};sourceButton.onclick=()=>switchTo(source);candidateButton.onclick=()=>switchTo(candidate);
seek.oninput=()=>{{if(Number.isFinite(active.duration))active.currentTime=active.duration*Number(seek.value)/1000}};loop.onchange=()=>{{source.loop=loop.checked;candidate.loop=loop.checked}};
for(const audio of [source,candidate]){{audio.ontimeupdate=sync;audio.onplay=()=>{{if(playingAudio&&playingAudio!==audio)playingAudio.pause();playingAudio=audio;other().pause();play.textContent='Pause'}};audio.onpause=()=>{{if(playingAudio===audio)playingAudio=null;if(other().paused)play.textContent='Play'}};audio.onended=()=>{{if(playingAudio===audio)playingAudio=null;const complete=completePlayback(audio);if(audio===source)s.dataset.sourceComplete=String(complete);else s.dataset.candidateComplete=String(complete);playback.textContent='Complete playback: source '+(s.dataset.sourceComplete==='true'?'done':'pending')+'; candidate '+(s.dataset.candidateComplete==='true'?'done':'pending')+(complete?'':' — seeking cannot replace full playback');play.textContent='Play';sync()}}}}
for(const [name,label] of [['artifacts','Codec artifacts / tonal / transient changes'],['noise_floor','Noise floor and low-level content'],['duration_tail','Complete duration, tail, and truncation'],['loop_boundary','Loop-boundary comparison']]){{const l=document.createElement('label');l.textContent=label;const t=document.createElement('textarea');t.dataset.field=name;l.append(t);s.append(l)}}
const v=document.createElement('label');v.textContent='Verdict';const select=document.createElement('select');select.dataset.field='verdict';select.innerHTML='<option value="">Select…</option><option value="passed">Passed</option><option value="failed">Failed</option>';v.append(select);s.append(v);root.append(s)}}
document.querySelector('#export').onclick=()=>{{const reviewer=document.querySelector('#reviewer').value.trim();const reviews=[];let missing=!reviewer;const reviewerValid=/^(?!.*--)[A-Za-z0-9](?:[A-Za-z0-9-]{{0,37}}[A-Za-z0-9])?$/.test(reviewer);const procedure={{headphones_checked:document.querySelector('#headphones').checked,representative_speakers_checked:document.querySelector('#speakers').checked,loop_boundaries_checked:document.querySelector('#loops').checked}};if(!Object.values(procedure).every(Boolean))missing=true;
const reviewFieldComplete=(name,value)=>name==='verdict'?['passed','failed'].includes(value):value.length>=8;
for(const section of document.querySelectorAll('.asset')){{const meta=assets.find(a=>a.logical_path===section.dataset.logical);const values={{logical_path:section.dataset.logical,source_sha256:meta.source_sha256,output_sha256:meta.output_sha256,review_evidence_path:meta.review_evidence_path,candidate_evidence:meta.candidate_evidence,source_playback_completed:section.dataset.sourceComplete==='true',candidate_playback_completed:section.dataset.candidateComplete==='true'}};if(!values.source_playback_completed||!values.candidate_playback_completed)missing=true;for(const field of section.querySelectorAll('[data-field]')){{const name=field.dataset.field;values[name]=field.value.trim();if(!reviewFieldComplete(name,values[name]))missing=true}}reviews.push(values)}}
if(missing){{alert('Complete both full playbacks, all procedure attestations, substantive notes, reviewer identity, and every verdict before export.');return}}
if(!reviewerValid){{alert('Use a valid GitHub username without a leading @.');return}}
const payload={{$schema:'https://atrinik.org/schemas/sound/critical-listening-review-v1.schema.json',schema_version:1,non_publishing:true,reviewed_by:reviewer,reviewed_at:new Date().toISOString().replace(/\\.\\d{{3}}Z$/,'Z'),source_tree:'{bundle["source_tree"]}',review_input_sha256:'{bundle["review_input_sha256"]}',toolchain_sha256:'{bundle["toolchain_sha256"]}',review_bundle_sha256:'{bundle["contract_sha256"]}',worksheet_contract_sha256:'{WORKSHEET_CONTRACT_PLACEHOLDER}',procedure,reviews}};
const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}}));const link=document.createElement('a');link.href=url;link.download='atrinik-critical-listening-review.json';link.click();URL.revokeObjectURL(url)}};</script>
</body></html>"""
    return document.encode("utf-8")


def review_bundle_html(bundle: dict[str, object]) -> bytes:
    template = review_bundle_html_template(bundle)
    contract_hash = hashlib.sha256(template).hexdigest().encode("ascii")
    placeholder = WORKSHEET_CONTRACT_PLACEHOLDER.encode("ascii")
    if template.count(placeholder) != 1:
        raise ReleaseError("critical-listening worksheet contract placeholder is invalid")
    return template.replace(placeholder, contract_hash)


def worksheet_contract_sha256(bundle: dict[str, object]) -> str:
    return hashlib.sha256(review_bundle_html_template(bundle)).hexdigest()


def command_build_review_bundle(arguments: argparse.Namespace) -> None:
    manifest = checked_manifest()
    validate_manifest(manifest)
    asset_class = getattr(arguments, "asset_class", None)
    selected = eligible_vorbis_review_assets(manifest, asset_class)
    if not selected:
        raise ReleaseError("no license-approved Vorbis sources await quality review")
    selected_classes = {str(asset["logical_path"]).partition("/")[0] for asset in selected}
    if len(selected_classes) != 1:
        raise ReleaseError("eligible reviews span asset classes; select --asset-class background or effects")
    output_directory = Path(arguments.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    if any(output_directory.iterdir()):
        raise ReleaseError(f"review-bundle output directory must be empty: {output_directory}")
    toolchain = checked_toolchain()
    versions = verify_toolchain(toolchain)
    bundle_assets: list[dict[str, object]] = []
    for asset in selected:
        logical_path = str(asset["logical_path"])
        source_relative = PurePosixPath("sources") / PurePosixPath(logical_path)
        source_output = output_directory / source_relative
        source_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / logical_path, source_output)
        candidate_root = output_directory / "candidates" / PurePosixPath(logical_path)
        evidence = write_review_candidate(asset, candidate_root, toolchain, versions)
        candidate_relative = candidate_root.relative_to(output_directory) / str(asset["generated_path"])
        bundle_assets.append({
            "logical_path": logical_path,
            "source_path": source_relative.as_posix(),
            "source_sha256": evidence["source_sha256"],
            "candidate_path": candidate_relative.as_posix(),
            "output_sha256": evidence["output_sha256"],
            "candidate_gain_db": evidence["measurements"]["rendered_pcm"]["applied_gain_db"],  # type: ignore[index]
            "review_evidence_path": (candidate_root.relative_to(output_directory) / "review-evidence.json").as_posix(),
            "candidate_evidence": evidence,
        })
    bundle = {
        "schema_version": 1,
        "non_publishing": True,
        "source_tree": source_revision("ATRINIK_SOURCE_TREE", "HEAD^{tree}"),
        "review_input_sha256": quality_review_input_sha256(selected),
        "toolchain_sha256": sha256(TOOLCHAIN),
        "assets": bundle_assets,
    }
    canonical_core = json.loads(canonical_json(bundle))
    assert isinstance(canonical_core, dict)
    bundle = canonical_core
    bundle["contract_sha256"] = hashlib.sha256(canonical_json(bundle)).hexdigest()
    bundle["worksheet_contract_sha256"] = worksheet_contract_sha256(bundle)
    worksheet = review_bundle_html(bundle)
    bundle["worksheet_sha256"] = hashlib.sha256(worksheet).hexdigest()
    bundle_bytes = canonical_json(bundle)
    atomic_write(output_directory / "review-bundle.json", bundle_bytes)
    atomic_write(output_directory / "index.html", worksheet)
    write_tree_checksums(output_directory)
    print(output_directory / "index.html")


def checked_bundle_file(root: Path, relative: object, label: str) -> Path:
    pure = PurePosixPath(str(relative))
    if not isinstance(relative, str) or pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative:
        raise ReleaseError(f"unsafe {label} path in review bundle: {relative}")
    path = root / pure
    current = root
    for part in pure.parts:
        current /= part
        if current.is_symlink():
            raise ReleaseError(f"symlink {label} path in review bundle: {relative}")
    if not path.is_file():
        raise ReleaseError(f"missing {label} file in review bundle: {relative}")
    return path


def verify_tree_checksums(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ReleaseError(f"review bundle must be a regular directory: {root}")
    checksum_path = checked_bundle_file(root, "SHA256SUMS", "checksum")
    recorded: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="ascii").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]) or parts[1] == "SHA256SUMS":
            raise ReleaseError("malformed review-bundle SHA256SUMS entry")
        if parts[1] in recorded:
            raise ReleaseError(f"duplicate review-bundle checksum entry: {parts[1]}")
        recorded[parts[1]] = parts[0]
    expected: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ReleaseError(f"review bundle contains a symlink: {path.relative_to(root)}")
        if path.is_file() and path != checksum_path:
            expected.add(path.relative_to(root).as_posix())
    if set(recorded) != expected:
        raise ReleaseError("review-bundle SHA256SUMS does not cover the exact file tree")
    for relative, expected_hash in recorded.items():
        if sha256(checked_bundle_file(root, relative, "checksummed")) != expected_hash:
            raise ReleaseError(f"review-bundle checksum mismatch: {relative}")


def verify_review_bundle_candidates(
    bundle_root: Path,
    bundle_by_path: dict[str, dict[str, object]],
    expected_by_path: dict[str, dict[str, object]],
) -> None:
    toolchain = checked_toolchain()
    versions = verify_toolchain(toolchain)
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-review-verify-") as temporary:
        verification_root = Path(temporary)
        for logical_path, bundled in bundle_by_path.items():
            candidate_root = verification_root / PurePosixPath(logical_path)
            reproduced = write_review_candidate(
                expected_by_path[logical_path], candidate_root, toolchain, versions,
            )
            reproduced_candidate = candidate_root / str(reproduced["generated_path"])
            bundled_candidate = checked_bundle_file(
                bundle_root, bundled["candidate_path"], "candidate",
            )
            if reproduced != bundled["candidate_evidence"] or not filecmp.cmp(
                reproduced_candidate, bundled_candidate, shallow=False,
            ):
                raise ReleaseError(
                    f"review-bundle candidate is not the deterministic current output: {logical_path}"
                )


def verify_review_bundle_result(bundle_root: Path, result: object) -> tuple[dict[str, object], list[dict[str, object]]]:
    verify_tree_checksums(bundle_root)
    bundle_value = read_json(bundle_root / "review-bundle.json")
    if not isinstance(bundle_value, dict) or set(bundle_value) != {
        "schema_version", "non_publishing", "review_input_sha256", "toolchain_sha256",
        "source_tree", "contract_sha256", "worksheet_contract_sha256", "worksheet_sha256", "assets",
    } or bundle_value.get("schema_version") != 1 or bundle_value.get("non_publishing") is not True:
        raise ReleaseError("invalid review-bundle manifest")
    if bundle_value.get("source_tree") != source_revision("ATRINIK_SOURCE_TREE", "HEAD^{tree}") or bundle_value.get("toolchain_sha256") != sha256(TOOLCHAIN):
        raise ReleaseError("review bundle is stale for the current source tree or toolchain manifest")
    bundle_assets = bundle_value.get("assets")
    if not isinstance(bundle_assets, list):
        raise ReleaseError("review-bundle assets must be an array")
    index_path = checked_bundle_file(bundle_root, "index.html", "listening worksheet")
    canonical_worksheet = review_bundle_html(bundle_value)
    if index_path.read_bytes() != canonical_worksheet or bundle_value.get("worksheet_contract_sha256") != worksheet_contract_sha256(bundle_value) or bundle_value.get("worksheet_sha256") != hashlib.sha256(canonical_worksheet).hexdigest():
        raise ReleaseError("review-bundle listening worksheet is not canonical")
    core_bundle = {key: value for key, value in bundle_value.items() if key not in {"contract_sha256", "worksheet_contract_sha256", "worksheet_sha256"}}
    if bundle_value.get("contract_sha256") != hashlib.sha256(canonical_json(core_bundle)).hexdigest():
        raise ReleaseError("review-bundle contract hash is not canonical")
    asset_classes = {
        str(asset.get("logical_path", "")).partition("/")[0]
        for asset in bundle_assets if isinstance(asset, dict)
    }
    if len(asset_classes) != 1 or not asset_classes <= {"background", "effects"}:
        raise ReleaseError("review bundle must contain exactly one asset class")
    asset_class = next(iter(asset_classes))
    current_manifest = checked_manifest()
    validate_manifest(current_manifest)
    expected_by_path = {
        str(asset["logical_path"]): asset
        for asset in eligible_vorbis_review_assets(current_manifest, asset_class)
    }
    if bundle_value.get("review_input_sha256") != quality_review_input_sha256(list(expected_by_path.values())):
        raise ReleaseError("review bundle is stale for the current review inputs")
    bundle_by_path: dict[str, dict[str, object]] = {}
    for asset in bundle_assets:
        if not isinstance(asset, dict) or set(asset) != {
            "logical_path", "source_path", "source_sha256", "candidate_path", "output_sha256",
            "candidate_gain_db", "review_evidence_path", "candidate_evidence",
        }:
            raise ReleaseError("invalid review-bundle asset entry")
        logical_path = str(asset["logical_path"])
        if logical_path in bundle_by_path:
            raise ReleaseError(f"duplicate review-bundle asset: {logical_path}")
        current_asset = expected_by_path.get(logical_path)
        if current_asset is None:
            raise ReleaseError(f"review-bundle asset is not currently eligible: {logical_path}")
        current_source = current_asset.get("source")
        assert isinstance(current_source, dict)
        expected_source_path = (PurePosixPath("sources") / PurePosixPath(logical_path)).as_posix()
        expected_evidence_path = (PurePosixPath("candidates") / PurePosixPath(logical_path) / "review-evidence.json").as_posix()
        expected_candidate_path = (PurePosixPath("candidates") / PurePosixPath(logical_path) / str(current_asset["generated_path"])).as_posix()
        if asset["source_path"] != expected_source_path or asset["source_sha256"] != current_source.get("sha256") or asset["review_evidence_path"] != expected_evidence_path or asset["candidate_path"] != expected_candidate_path:
            raise ReleaseError(f"review-bundle asset does not match the current manifest: {logical_path}")
        source = checked_bundle_file(bundle_root, asset["source_path"], "source")
        candidate = checked_bundle_file(bundle_root, asset["candidate_path"], "candidate")
        evidence_path = checked_bundle_file(bundle_root, asset["review_evidence_path"], "candidate evidence")
        evidence = read_json(evidence_path)
        if sha256(source) != asset["source_sha256"] or sha256(candidate) != asset["output_sha256"]:
            raise ReleaseError(f"review-bundle asset hash mismatch: {logical_path}")
        if not isinstance(evidence, dict) or evidence.get("logical_path") != logical_path or evidence.get("source_sha256") != asset["source_sha256"] or evidence.get("output_sha256") != asset["output_sha256"] or evidence.get("toolchain_sha256") != bundle_value["toolchain_sha256"] or evidence.get("non_publishing") is not True:
            raise ReleaseError(f"review-bundle evidence mismatch: {logical_path}")
        if evidence.get("generated_path") != current_asset["generated_path"]:
            raise ReleaseError(f"review-bundle generated path mismatch: {logical_path}")
        if asset["candidate_evidence"] != evidence:
            raise ReleaseError(f"review-bundle embedded evidence mismatch: {logical_path}")
        measurements = evidence.get("measurements")
        if not isinstance(measurements, dict) or not isinstance(measurements.get("rendered_pcm"), dict) or measurements["rendered_pcm"].get("applied_gain_db") != asset["candidate_gain_db"]:  # type: ignore[union-attr]
            raise ReleaseError(f"review-bundle gain evidence mismatch: {logical_path}")
        expected_candidate = (PurePosixPath(str(asset["review_evidence_path"])).parent / str(evidence.get("generated_path"))).as_posix()
        if expected_candidate != asset["candidate_path"]:
            raise ReleaseError(f"review-bundle candidate path mismatch: {logical_path}")
        bundle_by_path[logical_path] = asset
    if set(bundle_by_path) != set(expected_by_path):
        raise ReleaseError("review bundle does not contain the exact currently eligible asset set")

    validate_schema_instance(result, checked_schema("critical-listening-review-v1.schema.json"))
    assert isinstance(result, dict)
    if result.get("source_tree") != bundle_value["source_tree"] or result.get("review_input_sha256") != bundle_value["review_input_sha256"] or result.get("toolchain_sha256") != bundle_value["toolchain_sha256"] or result.get("review_bundle_sha256") != bundle_value["contract_sha256"] or result.get("worksheet_contract_sha256") != bundle_value["worksheet_contract_sha256"]:
        raise ReleaseError("critical-listening result is stale for the review bundle")
    try:
        reviewed_at = datetime.strptime(str(result["reviewed_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ReleaseError("critical-listening result has a non-canonical review timestamp") from exc
    if reviewed_at > datetime.now(UTC):
        raise ReleaseError("critical-listening result has a future review timestamp")
    reviews = result["reviews"]
    assert isinstance(reviews, list)
    reviews_by_path: dict[str, dict[str, object]] = {}
    for review in reviews:
        assert isinstance(review, dict)
        logical_path = str(review["logical_path"])
        if logical_path in reviews_by_path:
            raise ReleaseError(f"duplicate critical-listening result: {logical_path}")
        asset = bundle_by_path.get(logical_path)
        if asset is None or any(review[key] != asset[key] for key in (
            "source_sha256", "output_sha256", "review_evidence_path", "candidate_evidence",
        )):
            raise ReleaseError(f"critical-listening result does not match bundle: {logical_path}")
        reviews_by_path[logical_path] = review
    if set(reviews_by_path) != set(expected_by_path):
        raise ReleaseError("critical-listening result does not cover the exact review bundle")
    verify_review_bundle_candidates(bundle_root, bundle_by_path, expected_by_path)
    return bundle_value, [reviews_by_path[path] for path in sorted(reviews_by_path)]


def github_attestation_body(result_sha256: str) -> str:
    return f"Atrinik critical-listening attestation v1\nresult_sha256: {result_sha256}"


def checked_github_attestation(url: str, result: dict[str, object], result_sha256: str) -> None:
    match = re.fullmatch(r"https://github\.com/atrinik/sound/issues/(21|22)#issuecomment-([1-9][0-9]*)", url)
    if match is None:
        raise ReleaseError("critical-listening result lacks a valid GitHub attestation URL")
    issue_number, comment_id = match.groups()
    reviews = result.get("reviews")
    if not isinstance(reviews, list):
        raise ReleaseError("critical-listening result lacks review entries")
    asset_classes = {
        str(review.get("logical_path", "")).partition("/")[0]
        for review in reviews if isinstance(review, dict)
    }
    expected_issue = "22" if asset_classes == {"effects"} else "21" if asset_classes == {"background"} else None
    if issue_number != expected_issue:
        raise ReleaseError("GitHub attestation issue does not match the reviewed asset class")
    completed = run(["gh", "api", f"repos/atrinik/sound/issues/comments/{comment_id}"], capture=True)
    try:
        comment = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("GitHub returned an invalid critical-listening attestation") from exc
    expected_html_url = f"https://github.com/atrinik/sound/issues/{issue_number}#issuecomment-{comment_id}"
    expected_issue_url = f"https://api.github.com/repos/atrinik/sound/issues/{issue_number}"
    user = comment.get("user") if isinstance(comment, dict) else None
    node_id = comment.get("node_id") if isinstance(comment, dict) else None
    if not isinstance(comment, dict) or comment.get("html_url") != expected_html_url or comment.get("issue_url") != expected_issue_url or comment.get("author_association") not in {"OWNER", "MEMBER", "COLLABORATOR"} or not isinstance(user, dict) or user.get("login") != result.get("reviewed_by") or not isinstance(node_id, str) or not node_id or str(comment.get("body", "")).strip() != github_attestation_body(result_sha256):
        raise ReleaseError("GitHub critical-listening attestation does not match the review result")
    try:
        comment_time = datetime.strptime(str(comment["created_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        updated_time = datetime.strptime(str(comment["updated_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        review_time = datetime.strptime(str(result["reviewed_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (KeyError, ValueError) as exc:
        raise ReleaseError("GitHub critical-listening attestation has an invalid timestamp") from exc
    if updated_time != comment_time:
        raise ReleaseError("GitHub critical-listening attestation comment was edited")
    edit_completed = run([
        "gh", "api", "graphql",
        "-f", "query=query($id:ID!){node(id:$id){... on IssueComment{lastEditedAt}}}",
        "-F", f"id={node_id}",
    ], capture=True)
    try:
        edit_state = json.loads(edit_completed.stdout)
        edit_node = edit_state["data"]["node"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReleaseError("GitHub returned invalid critical-listening edit metadata") from exc
    if not isinstance(edit_node, dict) or "lastEditedAt" not in edit_node:
        raise ReleaseError("GitHub returned invalid critical-listening edit metadata")
    if edit_node["lastEditedAt"] is not None:
        raise ReleaseError("GitHub critical-listening attestation comment was edited")
    reviewer = str(result["reviewed_by"])
    permission_completed = run([
        "gh", "api", f"repos/atrinik/sound/collaborators/{reviewer}/permission",
    ], capture=True)
    try:
        permission = json.loads(permission_completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError("GitHub returned an invalid reviewer permission") from exc
    if not isinstance(permission, dict) or permission.get("permission") not in {"write", "admin"} or not isinstance(permission.get("role_name"), str):
        raise ReleaseError("critical-listening reviewer lacks repository write permission")
    age_seconds = (comment_time - review_time).total_seconds()
    if age_seconds < 0 or age_seconds > 24 * 60 * 60:
        raise ReleaseError("critical-listening result timestamp is not bound to its GitHub attestation")


def verify_quality_review_attestations(reviews: dict[str, dict[str, object]]) -> None:
    verified: set[tuple[str, str]] = set()
    for entry in reviews.values():
        evidence = entry["evidence"]
        assert isinstance(evidence, dict)
        locator = str(evidence["artifact_locator"])
        result_hash = str(evidence["artifact_sha256"])
        url = str(evidence["github_attestation_url"])
        key = (url, result_hash)
        if key in verified:
            continue
        result = checked_critical_listening_result(ROOT / locator)
        checked_github_attestation(url, result, result_hash)
        verified.add(key)


def proposed_quality_review_ledger(
    bundle: dict[str, object],
    result: dict[str, object],
    reviews: list[dict[str, object]],
    artifact_locator: str,
    artifact_sha256: str,
    github_attestation_url: str,
) -> dict[str, object]:
    existing = checked_quality_reviews()
    entries = list(existing.values())
    for review in reviews:
        if review["verdict"] != "passed":
            continue
        logical_path = str(review["logical_path"])
        if logical_path in existing:
            raise ReleaseError(f"quality review already exists: {logical_path}")
        entries.append({
            "logical_path": logical_path,
            "status": "passed",
            "source_sha256": review["source_sha256"],
            "toolchain_sha256": bundle["toolchain_sha256"],
            "output_sha256": review["output_sha256"],
            "reviewed_by": result["reviewed_by"],
            "reviewed_at": result["reviewed_at"],
            "evidence": {
                "method": "critical-listening",
                "artifact_locator": artifact_locator,
                "artifact_sha256": artifact_sha256,
                "github_attestation_url": github_attestation_url,
                "notes": "Complete per-category notes and verdict are preserved in the hash-bound review artifact.",
            },
        })
    document = {
        "$schema": "../schemas/vorbis-quality-reviews-v2.schema.json",
        "schema_version": 2,
        "reviews": sorted(entries, key=lambda entry: str(entry["logical_path"])),
    }
    validate_schema_instance(document, checked_schema("vorbis-quality-reviews-v2.schema.json"))
    return document


def command_prepare_quality_review(arguments: argparse.Namespace) -> None:
    locator = str(arguments.evidence_locator)
    pure = PurePosixPath(locator)
    if not locator.startswith("evidence/") or pure.is_absolute() or ".." in pure.parts or pure.as_posix() != locator:
        raise ReleaseError("critical-listening result must use a repository-owned evidence locator")
    evidence_path = ROOT / pure
    result = read_json(evidence_path)
    result_sha256 = sha256(evidence_path)
    verify_review_artifact({"artifact_locator": locator, "artifact_sha256": result_sha256}, "critical-listening bundle")
    bundle, reviews = verify_review_bundle_result(Path(arguments.bundle_directory), result)
    assert isinstance(result, dict)
    github_attestation_url = str(arguments.github_attestation_url)
    checked_github_attestation(github_attestation_url, result, result_sha256)
    print(canonical_json(proposed_quality_review_ledger(
        bundle, result, reviews, locator, result_sha256, github_attestation_url,
    )).decode("utf-8"), end="")


def verify_quality_review_outputs(reviews: dict[str, dict[str, object]]) -> None:
    if not reviews:
        return
    manifest = checked_manifest()
    assets = manifest.get("assets")
    assert isinstance(assets, list)
    current_by_path = {
        str(asset["logical_path"]): asset for asset in assets if isinstance(asset, dict)
    }
    toolchain = checked_toolchain()
    versions = verify_toolchain(toolchain)
    results: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-quality-verify-") as temporary:
        output_root = Path(temporary)
        for logical_path, entry in reviews.items():
            evidence = entry["evidence"]
            assert isinstance(evidence, dict)
            locator = str(evidence["artifact_locator"])
            if locator not in results:
                results[locator] = checked_critical_listening_result(ROOT / locator)
            result = results[locator]
            result_reviews = result["reviews"]
            assert isinstance(result_reviews, list)
            matches = [
                review for review in result_reviews
                if isinstance(review, dict) and review.get("logical_path") == logical_path
            ]
            current = current_by_path.get(logical_path)
            if len(matches) != 1 or current is None:
                raise ReleaseError(f"quality-review output lacks a current source: {logical_path}")
            candidate_root = output_root / PurePosixPath(logical_path)
            reproduced = write_review_candidate(current, candidate_root, toolchain, versions)
            if reproduced != matches[0].get("candidate_evidence") or reproduced.get("output_sha256") != entry.get("output_sha256"):
                raise ReleaseError(f"quality-review output is not the deterministic current candidate: {logical_path}")


def command_validate_quality_outputs(_arguments: argparse.Namespace) -> None:
    reviews = checked_quality_reviews()
    verify_quality_review_outputs(reviews)
    print(f"validated {len(reviews)} deterministic quality-review outputs")


def command_validate(_arguments: argparse.Namespace) -> None:
    manifest = checked_manifest()
    blockers = validate_manifest(manifest, verify_tracked=True)
    verify_quality_review_attestations(checked_quality_reviews())
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
    quality_outputs = commands.add_parser(
        "validate-quality-outputs",
        help="reproduce every committed quality-review candidate in the pinned toolchain",
    )
    quality_outputs.set_defaults(function=command_validate_quality_outputs)
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
    bundle = commands.add_parser("build-review-bundle", help="build all eligible non-publishing Vorbis candidates and a listening worksheet")
    bundle.add_argument("output_directory")
    bundle.add_argument(
        "--asset-class", choices=("background", "effects"),
        help="build one asset class when both backgrounds and effects are eligible",
    )
    bundle.set_defaults(function=command_build_review_bundle)
    prepare_review = commands.add_parser("prepare-quality-review", help="verify a completed listening bundle and print the proposed quality-review ledger")
    prepare_review.add_argument("bundle_directory")
    prepare_review.add_argument("evidence_locator")
    prepare_review.add_argument("github_attestation_url")
    prepare_review.set_defaults(function=command_prepare_quality_review)
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
