#!/usr/bin/env python3
"""Build and validate deterministic Atrinik sound release artifacts."""

from __future__ import annotations

import argparse
import copy
import contextlib
import ctypes
import dataclasses
import enum
import errno
import fcntl
import filecmp
import functools
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import wave
from datetime import UTC, datetime
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
GIT_REPOSITORY = ROOT
SOURCE_MANIFEST = ROOT / "manifests" / "source-assets.json"
TOOLCHAIN = ROOT / "manifests" / "audio-toolchain.json"
PLAYTEST_TOOLCHAIN = ROOT / "manifests" / "playtest-audio-toolchain.json"
CLASSIC_TOOLCHAIN = ROOT / "manifests" / "classic-audio-toolchain.json"
FIXTURE_PLAN = ROOT / "manifests" / "fixture-plan.json"
QUALITY_REVIEWS = ROOT / "manifests" / "vorbis-quality-reviews.json"
LICENSE_REVIEWS = ROOT / "manifests" / "license-reviews.json"
TRACKER_DURATIONS = ROOT / "manifests" / "tracker-durations.json"
SOURCE_REPLACEMENTS = ROOT / "manifests" / "source-replacements.json"
SCHEMA_ROOT = ROOT / "schemas"
PLAYTEST_MANIFEST_NAME = "playtest-manifest.json"
PLAYTEST_BLOCKERS_NAME = "playtest-blockers.json"
PLAYTEST_ROOT_LOCK_NAME = "atrinik-playtest-builds.lock"
PLAYTEST_ROOT_LOCK_MARKER = b"atrinik-sound-playtest-builds-v1\n"
PLAYTEST_MARKER_NAME = ".atrinik-playtest-tree.json"
PLAYTEST_MARKER = {
    "format": "atrinik-sound-playtest-tree",
    "playtest_only": True,
    "publishable": False,
    "schema_version": 1,
}
CLASSIC_RUNTIME_MANIFEST_NAME = "classic-runtime-manifest.json"
CLASSIC_RUNTIME_REMEDIATION_NAME = "classic-runtime-remediation.json"
CLASSIC_RUNTIME_SCHEMA_NAME = "classic-runtime-manifest-v1.schema.json"
CLASSIC_REMEDIATION_SCHEMA_NAME = "classic-remediation-v1.schema.json"
CLASSIC_RUNTIME_MAX_FILES = 512
CLASSIC_RUNTIME_MAX_FILE_BYTES = 64 * 1024 * 1024
CLASSIC_RUNTIME_MAX_TOTAL_BYTES = 512 * 1024 * 1024
AUDIO_SUFFIXES = {".flac", ".mid", ".mod", ".s3m", ".xm", ".ogg"}
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
    'Nooskewl / troutsneeze - https://opengameart.org/content/42-monster-rpg-2-music-tracks - CC0': ("CC0-1.0", "licenses/CC0-1.0.txt"),
}


class ReleaseError(RuntimeError):
    """A release contract violation with an operator-facing diagnostic."""


class SourceIntegrityError(ReleaseError):
    """A tracked checkout differs from its claimed immutable Git tree."""


class PlaytestVerificationMode(enum.Enum):
    """Fixed verification work budgets for the playtest-tree trust stages."""

    BUILT_TREE = (False, False, True)
    PAIRED_TREE = (False, True, True)
    EXISTING_TREE = (True, True, False)

    def __init__(
        self, reproduce_conversions: bool, decode_payloads: bool,
        trusted_snapshot_only: bool,
    ) -> None:
        self.reproduce_conversions = reproduce_conversions
        self.decode_payloads = decode_payloads
        self.trusted_snapshot_only = trusted_snapshot_only


@dataclasses.dataclass(frozen=True)
class SourceMetadata:
    duration_seconds: float
    sample_rate: int | None
    channels: int | None


@dataclasses.dataclass(frozen=True)
class PlaytestSnapshotGuard:
    path: Path
    mutation_descriptor: int
    root_watch_descriptor: int

    def reject_mutations(self) -> None:
        reject_playtest_mutations(self.mutation_descriptor)


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


def logical_tree_sha256(root: Path, logical_paths: list[str]) -> str:
    digest = hashlib.sha256()
    for logical_path in sorted(logical_paths):
        digest.update(f"{sha256(root / logical_path)}  {logical_path}\n".encode("ascii"))
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
    negated = schema.get("not")
    if isinstance(negated, dict):
        try:
            validate_schema_instance(instance, negated, root=root, location=location)
        except ReleaseError:
            pass
        else:
            raise ReleaseError(f"schema not mismatch at {location}")
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
        dependent_required = schema.get("dependentRequired", {})
        if not isinstance(dependent_required, dict):
            raise ReleaseError(f"invalid dependentRequired at {location}")
        for key, dependencies in dependent_required.items():
            if key in instance and (
                not isinstance(dependencies, list)
                or any(dependency not in instance for dependency in dependencies)
            ):
                raise ReleaseError(f"schema dependent field missing at {location}.{key}")
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


def _replacement_object_type(
    commit: str, repository: str, environment: dict[str, str],
) -> str:
    try:
        return subprocess.run(
            ["git", "cat-file", "-t", commit],
            check=True,
            cwd=repository,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseError("replacement predecessor object is unavailable") from exc


def _fetch_replacement_predecessor(
    commit: str, repository: str, environment: dict[str, str],
) -> None:
    try:
        subprocess.run(
            ["git", "fetch", "--no-tags", "--no-write-fetch-head", "origin", commit],
            check=True,
            cwd=repository,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
            check=True,
            cwd=repository,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseError("cannot fetch the exact replacement predecessor commit") from exc
    if resolved != commit:
        raise ReleaseError("fetched replacement predecessor does not match its requested commit")


@functools.cache
def archived_source_hashes(
    commit: str, logical_paths: tuple[str, ...], repository: str,
) -> dict[str, str]:
    environment = exact_git_environment()
    try:
        object_type = _replacement_object_type(commit, repository, environment)
    except ReleaseError:
        _fetch_replacement_predecessor(commit, repository, environment)
        object_type = _replacement_object_type(commit, repository, environment)
    if object_type != "commit":
        raise ReleaseError("replacement predecessor coordinate is not a commit")
    try:
        archive = subprocess.run(
            ["git", "archive", "--format=tar", commit, "--", *logical_paths],
            check=True,
            cwd=repository,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseError("cannot read replacement predecessor sources from the verified commit") from exc
    hashes: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
            for member in stream.getmembers():
                if member.isdir():
                    continue
                if not member.isfile() or member.name not in logical_paths:
                    raise ReleaseError("replacement predecessor archive has an unexpected member")
                source = stream.extractfile(member)
                if source is None:
                    raise ReleaseError("replacement predecessor archive member cannot be read")
                hashes[member.name] = hashlib.sha256(source.read()).hexdigest()
    except tarfile.TarError as exc:
        raise ReleaseError("replacement predecessor archive is not a valid complete archive") from exc
    if set(hashes) != set(logical_paths):
        raise ReleaseError("replacement predecessor archive does not cover every removed source")
    return hashes


def checked_source_replacements(
    *, allow_missing_historical: bool = False,
) -> dict[str, dict[str, object]]:
    if allow_missing_historical and not SOURCE_REPLACEMENTS.exists():
        return {}
    schema = checked_schema("source-replacements-v1.schema.json")
    value = read_json(SOURCE_REPLACEMENTS)
    if (
        not isinstance(value, dict)
        or set(value) != {"$schema", "schema_version", "replaced_source_commit", "replacements"}
        or value.get("$schema") != "../schemas/source-replacements-v1.schema.json"
        or value.get("schema_version") != 1
        or not isinstance(value.get("replacements"), list)
    ):
        raise ReleaseError("source-replacement ledger must use the complete version 1 contract")
    validate_schema_instance(value, schema)
    replacements: dict[str, dict[str, object]] = {}
    logical_paths: set[str] = set()
    for replacement in value["replacements"]:
        assert isinstance(replacement, dict)
        source_path = str(replacement["source_path"])
        logical_path = str(replacement["logical_path"])
        if source_path in replacements:
            raise ReleaseError(f"duplicate replacement source path: {source_path}")
        if logical_path in logical_paths:
            raise ReleaseError(f"duplicate replacement logical path: {logical_path}")
        source = ROOT / source_path
        legacy = ROOT / logical_path
        if source.is_symlink() or not source.is_file():
            raise ReleaseError(f"replacement source is missing or not a regular file: {source_path}")
        if legacy.exists():
            raise ReleaseError(f"replacement leaves legacy source present: {logical_path}")
        replacements[source_path] = {
            **replacement,
            "replaced_source_commit": value["replaced_source_commit"],
        }
        logical_paths.add(logical_path)
    if git_metadata_available():
        predecessor_hashes = archived_source_hashes(
            str(value["replaced_source_commit"]), tuple(sorted(logical_paths)),
            str(GIT_REPOSITORY),
        )
        for replacement in replacements.values():
            logical_path = str(replacement["logical_path"])
            if replacement["replaced_source_sha256"] != predecessor_hashes[logical_path]:
                raise ReleaseError(f"replacement removed-source hash mismatch: {logical_path}")
    elif os.environ.get("ATRINIK_RELEASE_INPUT_ATTESTED") != "1":
        raise ReleaseError("replacement predecessor hashes require Git metadata")
    return replacements


def source_coordinates(
    *, allow_missing_historical_replacements: bool = False,
) -> list[tuple[str, Path, dict[str, object] | None]]:
    replacements = checked_source_replacements(
        allow_missing_historical=allow_missing_historical_replacements,
    )
    coordinates: list[tuple[str, Path, dict[str, object] | None]] = []
    logical_paths: set[str] = set()
    discovered_paths: set[str] = set()
    for path in discover_sources():
        source_path = path.relative_to(ROOT).as_posix()
        discovered_paths.add(source_path)
        replacement = replacements.get(source_path)
        logical_path = str(replacement["logical_path"]) if replacement is not None else source_path
        if logical_path in logical_paths:
            raise ReleaseError(f"duplicate discovered logical path: {logical_path}")
        logical_paths.add(logical_path)
        coordinates.append((logical_path, path, replacement))
    missing = set(replacements) - discovered_paths
    if missing:
        raise ReleaseError(f"replacement ledger references undiscovered sources: {', '.join(sorted(missing))}")
    return coordinates


def ensure_sources_tracked(sources: list[Path]) -> None:
    try:
        completed = run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "background", "effects"],
            capture=True,
        )
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


def flac_metadata(path: Path) -> SourceMetadata:
    with path.open("rb") as stream:
        data = stream.read(42)
    if len(data) < 42 or data[:4] != b"fLaC":
        raise ReleaseError(f"invalid FLAC source: {path.relative_to(ROOT)}")
    block_type = data[4] & 0x7F
    block_length = int.from_bytes(data[5:8], "big")
    if block_type != 0 or block_length != 34 or len(data) < 8 + block_length:
        raise ReleaseError(f"FLAC source lacks a canonical STREAMINFO block: {path.relative_to(ROOT)}")
    packed = int.from_bytes(data[18:26], "big")
    sample_rate = (packed >> 44) & 0xFFFFF
    channels = ((packed >> 41) & 0x7) + 1
    total_samples = packed & ((1 << 36) - 1)
    if sample_rate <= 0 or channels not in {1, 2} or total_samples <= 0:
        raise ReleaseError(f"invalid FLAC stream metadata: {path.relative_to(ROOT)}")
    return SourceMetadata(round(total_samples / sample_rate, 6), sample_rate, channels)


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


def exact_git_environment() -> dict[str, str]:
    """Return an environment that resolves the repository's real object graph."""
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_CONFIG_COUNT"] = "2"
    environment["GIT_CONFIG_KEY_0"] = "core.fsmonitor"
    environment["GIT_CONFIG_VALUE_0"] = "false"
    environment["GIT_CONFIG_KEY_1"] = "core.untrackedCache"
    environment["GIT_CONFIG_VALUE_1"] = "false"
    return environment


def require_selected_git_worktree(environment: dict[str, str]) -> None:
    """Bind Git metadata operations to the selected checkout directory."""
    top_level_value = run(
        ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
        capture=True,
        env=environment,
    ).stdout.strip()
    try:
        expected_root = ROOT.stat()
        reported_root = Path(top_level_value).stat()
    except OSError as exc:
        raise SourceIntegrityError("cannot establish the selected Git worktree root") from exc
    if (expected_root.st_dev, expected_root.st_ino) != (
        reported_root.st_dev, reported_root.st_ino,
    ):
        raise SourceIntegrityError("Git worktree root differs from the selected sound checkout")


LFS_POINTER_VERSION = "version https://git-lfs.github.com/spec/v1"
LFS_POINTER_MAX_BYTES = 4096


def committed_lfs_paths(
    commit: str, paths: list[str], environment: dict[str, str],
) -> set[str]:
    if not paths:
        return set()
    try:
        output = run(
            [
                "git", "-C", str(ROOT), "-c", "core.attributesFile=/dev/null",
                "check-attr", f"--source={commit}", "-z", "filter", "--", *paths,
            ],
            capture=True,
            env=environment,
        ).stdout
    except ReleaseError as exc:
        raise SourceIntegrityError("cannot resolve committed LFS attributes") from exc
    fields = output.rstrip("\0").split("\0") if output else []
    if len(fields) % 3 != 0:
        raise SourceIntegrityError("cannot parse committed LFS attributes")
    values: dict[str, str] = {}
    for offset in range(0, len(fields), 3):
        path, attribute, value = fields[offset:offset + 3]
        if attribute != "filter" or path in values:
            raise SourceIntegrityError("cannot parse committed LFS attributes")
        values[path] = value
    if set(values) != set(paths):
        raise SourceIntegrityError("committed LFS attributes do not cover the exact source tree")
    return {path for path, value in values.items() if value == "lfs"}


def committed_blob_payload(
    object_id: str, environment: dict[str, str], relative: str,
) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "blob", object_id],
            check=True,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SourceIntegrityError(f"cannot read the committed LFS pointer: {relative}") from exc


def parse_lfs_pointer(payload: bytes, relative: str) -> tuple[str, int]:
    if len(payload) > LFS_POINTER_MAX_BYTES or not payload.endswith(b"\n"):
        raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}")
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}") from exc
    lines = text.split("\n")
    if not lines or lines[-1] != "" or lines[0] != LFS_POINTER_VERSION:
        raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}")
    values: dict[str, str] = {}
    for line in lines[1:-1]:
        key, separator, value = line.partition(" ")
        if not separator or not key or not value or key in values:
            raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}")
        if key not in {"oid", "size"} and not key.startswith("ext-"):
            raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}")
        values[key] = value
    oid = values.get("oid")
    size_value = values.get("size")
    if oid is None or size_value is None:
        raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}")
    oid_match = re.fullmatch(r"sha256:([0-9a-f]{64})", oid)
    if oid_match is None or re.fullmatch(r"[0-9]+", size_value) is None:
        raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}")
    return oid_match.group(1), int(size_value)


def ensure_exact_tracked_tree(commit: str) -> None:
    """Reject hidden index flags and bind every tracked byte/mode to a tree."""
    environment = exact_git_environment()
    flags = run(
        ["git", "-C", str(ROOT), "ls-files", "-v", "-z"], capture=True,
        env=environment,
    ).stdout
    for entry in flags.rstrip("\0").split("\0") if flags else []:
        if len(entry) < 3 or entry[1] != " ":
            raise SourceIntegrityError("cannot parse tracked source flags")
        if entry[0] == "S" or entry[0].islower():
            raise SourceIntegrityError(f"tracked source has a hidden index flag: {entry[2:]}")

    tree = run(
        ["git", "-C", str(ROOT), "ls-tree", "-r", "-z", "--full-tree", commit],
        capture=True,
        env=environment,
    ).stdout
    parsed_tree: list[tuple[str, str, str, str]] = []
    for entry in tree.rstrip("\0").split("\0") if tree else []:
        metadata, separator, relative = entry.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise SourceIntegrityError("cannot parse exact source tree")
        mode, kind, expected_object = fields
        if kind != "blob":
            continue
        parsed_tree.append((mode, expected_object, relative, entry))
    lfs_paths = committed_lfs_paths(
        commit,
        [relative for mode, _expected_object, relative, _entry in parsed_tree if mode in {"100644", "100755"}],
        environment,
    )
    for mode, expected_object, relative, _entry in parsed_tree:
        path = ROOT / relative
        try:
            before = path.lstat()
            if mode == "120000":
                if not stat.S_ISLNK(before.st_mode):
                    raise SourceIntegrityError(f"tracked source mode differs from {commit}: {relative}")
                payload = os.fsencode(os.readlink(path))
                after = path.lstat()
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise SourceIntegrityError(f"tracked source changed while hashing: {relative}")
                digest = hashlib.sha1(
                    f"blob {len(payload)}\0".encode("ascii") + payload,
                    usedforsecurity=False,
                ).hexdigest()
            else:
                if mode not in {"100644", "100755"} or not stat.S_ISREG(before.st_mode):
                    raise SourceIntegrityError(f"tracked source mode differs from {commit}: {relative}")
                if bool(before.st_mode & stat.S_IXUSR) != (mode == "100755"):
                    raise SourceIntegrityError(f"tracked source mode differs from {commit}: {relative}")
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    opened = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    ):
                        raise SourceIntegrityError(f"tracked source changed while hashing: {relative}")
                    lfs_pointer = None
                    if relative in lfs_paths:
                        lfs_pointer = committed_blob_payload(expected_object, environment, relative)
                        if len(lfs_pointer) > LFS_POINTER_MAX_BYTES:
                            raise SourceIntegrityError(f"tracked LFS pointer is malformed: {relative}")
                        expected_lfs_oid, expected_lfs_size = parse_lfs_pointer(lfs_pointer, relative)
                        digest_builder = hashlib.sha256()
                    else:
                        expected_lfs_oid = None
                        expected_lfs_size = None
                        digest_builder = hashlib.sha1(usedforsecurity=False)
                        digest_builder.update(f"blob {opened.st_size}\0".encode("ascii"))
                    prefix = bytearray()
                    with os.fdopen(os.dup(descriptor), "rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest_builder.update(chunk)
                            if lfs_pointer is not None and len(prefix) < len(lfs_pointer):
                                prefix.extend(chunk[:len(lfs_pointer) - len(prefix)])
                    digest = digest_builder.hexdigest()
                finally:
                    os.close(descriptor)
        except OSError as exc:
            raise SourceIntegrityError(f"cannot verify tracked source against {commit}: {relative}") from exc
        if relative in lfs_paths:
            assert expected_lfs_oid is not None and expected_lfs_size is not None
            if before.st_size == len(lfs_pointer) and bytes(prefix) == lfs_pointer:
                raise SourceIntegrityError(f"tracked LFS source is not hydrated: {relative}")
            if digest != expected_lfs_oid or before.st_size != expected_lfs_size:
                raise SourceIntegrityError(f"hydrated LFS source bytes differ from {commit}: {relative}")
        elif digest != expected_object:
            raise SourceIntegrityError(f"tracked source bytes differ from {commit}: {relative}")


def clean_source_coordinates() -> tuple[str, str]:
    """Return immutable coordinates for a clean, Git-backed local checkout."""
    try:
        environment = exact_git_environment()
        require_selected_git_worktree(environment)
        graft_path_value = run(
            ["git", "-C", str(ROOT), "rev-parse", "--git-path", "info/grafts"],
            capture=True,
            env=environment,
        ).stdout.strip()
        graft_path = Path(graft_path_value)
        if not graft_path.is_absolute():
            graft_path = ROOT / graft_path
        if graft_path.is_file() and graft_path.read_bytes().strip():
            raise SourceIntegrityError("legacy Git grafts cannot establish exact source coordinates")
        status_before = run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"],
            capture=True,
            env=environment,
        ).stdout
        commit = run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture=True,
            env=environment,
        ).stdout.strip()
        tree = run(
            ["git", "-C", str(ROOT), "rev-parse", f"{commit}^{{tree}}"],
            capture=True,
            env=environment,
        ).stdout.strip()
        ensure_exact_tracked_tree(commit)
        status_after = run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"],
            capture=True,
            env=environment,
        ).stdout
        ensure_exact_tracked_tree(commit)
        final_commit = run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture=True,
            env=environment,
        ).stdout.strip()
    except SourceIntegrityError:
        raise
    except ReleaseError as exc:
        raise ReleaseError("sound generation requires Git metadata") from exc
    if status_before or status_after:
        raise ReleaseError("sound source worktree is not clean")
    if commit != final_commit:
        raise ReleaseError("playtest-tree source HEAD changed while reading its coordinates")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ReleaseError("playtest-tree source coordinates are not full Git object IDs")
    return commit, tree


@contextlib.contextmanager
def anchored_playtest_output(path: Path, *, create_parents: bool) -> Iterator[tuple[Path, Path]]:
    """Retain no-follow directory handles for every output ancestor."""
    requested = path if path.is_absolute() else Path.cwd() / path
    lexical = Path(os.path.normpath(requested))
    build_path = ROOT / "build"
    try:
        relative = lexical.relative_to(build_path)
    except ValueError as exc:
        raise ReleaseError(f"playtest output must be below {build_path}") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseError("playtest output must be a directory below build/, not build/ itself")
    try:
        run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", "--", lexical.relative_to(ROOT).as_posix()],
            capture=True,
        )
    except (ValueError, ReleaseError) as exc:
        raise ReleaseError(f"playtest output is not ignored local build state: {lexical}") from exc
    try:
        build_path.mkdir(exist_ok=True)
        descriptor = os.open(build_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (FileExistsError, NotADirectoryError, OSError) as exc:
        raise ReleaseError(f"playtest build root is not a safe directory: {build_path}") from exc
    descriptors = [descriptor]
    try:
        for part in relative.parts[:-1]:
            if create_parents:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=descriptor)
                except FileExistsError:
                    pass
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            except OSError as exc:
                raise ReleaseError(f"playtest output ancestry is not a safe directory: {lexical.parent}") from exc
            descriptors.append(child)
            descriptor = child
        parent = Path(f"/proc/self/fd/{descriptor}")
        yield parent / relative.name, lexical
        ancestry = [build_path, *(build_path.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts)))]
        for candidate, opened in zip(ancestry, descriptors, strict=True):
            expected = os.fstat(opened)
            try:
                current = os.stat(candidate, follow_symlinks=False)
            except OSError as exc:
                raise ReleaseError("playtest output ancestry changed during operation") from exc
            if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
                raise ReleaseError("playtest output ancestry changed during operation")
    finally:
        for opened in reversed(descriptors):
            os.close(opened)


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
    if suffix == ".flac":
        return flac_metadata(path)
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


@contextlib.contextmanager
def archived_repository_tree(source_tree: str) -> Iterator[Path]:
    try:
        archive = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", source_tree],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"")
        rendered = detail.decode("utf-8", errors="replace").strip() if isinstance(detail, bytes) else str(detail)
        raise ReleaseError(f"cannot archive critical-listening source tree: {rendered}") from exc
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
            members = stream.getmembers()
            for member in members:
                pure = PurePosixPath(member.name)
                if pure.is_absolute() or ".." in pure.parts or not (member.isdir() or member.isfile()):
                    raise ReleaseError("critical-listening source tree contains an unsafe archive member")
            stream.extractall(root, members=members)
        toolchain = read_json(root / "manifests" / "audio-toolchain.json")
        tools = toolchain.get("tools") if isinstance(toolchain, dict) else None
        probe = tools.get("sdl3_mixer_probe") if isinstance(tools, dict) else None
        probe_source = probe.get("source_path") if isinstance(probe, dict) else None
        timidity = tools.get("timidity") if isinstance(tools, dict) else None
        deterministic_seed = timidity.get("deterministic_seed") if isinstance(timidity, dict) else None
        seed_source = deterministic_seed.get("source_path") if isinstance(deterministic_seed, dict) else None
        required_export_ignored = ["tools/audio/Dockerfile", probe_source]
        if seed_source is not None:
            required_export_ignored.append(seed_source)
        if isinstance(tools, dict):
            required_export_ignored.extend(
                contract["source_path"] for contract in tools.values()
                if isinstance(contract, dict) and isinstance(contract.get("source_path"), str)
            )
        for relative in dict.fromkeys(required_export_ignored):
            pure = PurePosixPath(str(relative))
            if not isinstance(relative, str) or pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative:
                raise ReleaseError("critical-listening source tree has an unsafe toolchain path")
            destination = root / relative
            try:
                payload = subprocess.run(
                    ["git", "-C", str(ROOT), "show", f"{source_tree}:{relative}"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ).stdout
            except (OSError, subprocess.CalledProcessError) as exc:
                raise ReleaseError(f"critical-listening source tree lacks required toolchain input: {relative}") from exc
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        yield root


@contextlib.contextmanager
def repository_root(root: Path) -> Iterator[None]:
    global ROOT, SOURCE_MANIFEST, TOOLCHAIN, FIXTURE_PLAN, QUALITY_REVIEWS
    global LICENSE_REVIEWS, TRACKER_DURATIONS, SOURCE_REPLACEMENTS, SCHEMA_ROOT
    previous = (
        ROOT, SOURCE_MANIFEST, TOOLCHAIN, FIXTURE_PLAN, QUALITY_REVIEWS,
        LICENSE_REVIEWS, TRACKER_DURATIONS, SOURCE_REPLACEMENTS, SCHEMA_ROOT,
    )
    ROOT = root
    SOURCE_MANIFEST = root / "manifests" / "source-assets.json"
    TOOLCHAIN = root / "manifests" / "audio-toolchain.json"
    FIXTURE_PLAN = root / "manifests" / "fixture-plan.json"
    QUALITY_REVIEWS = root / "manifests" / "vorbis-quality-reviews.json"
    LICENSE_REVIEWS = root / "manifests" / "license-reviews.json"
    TRACKER_DURATIONS = root / "manifests" / "tracker-durations.json"
    SOURCE_REPLACEMENTS = root / "manifests" / "source-replacements.json"
    SCHEMA_ROOT = root / "schemas"
    try:
        yield
    finally:
        (
            ROOT, SOURCE_MANIFEST, TOOLCHAIN, FIXTURE_PLAN, QUALITY_REVIEWS,
            LICENSE_REVIEWS, TRACKER_DURATIONS, SOURCE_REPLACEMENTS, SCHEMA_ROOT,
        ) = previous


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
        with archived_repository_tree(source_tree) as snapshot_root, repository_root(snapshot_root):
            expected = build_source_manifest(allow_historical_toolchain=True)
        if canonical_json(snapshot) != canonical_json(expected):
            raise ReleaseError("critical-listening source tree has a non-canonical source manifest")
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
            "source_path": (
                PurePosixPath("sources") / PurePosixPath(str(current["source_path"]))
            ).as_posix(),
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
    expected_assets = eligible_quality_review_assets(snapshot_manifest, asset_class)
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
    verified_result: dict[str, object] | None = None,
) -> None:
    result = verified_result
    if result is None:
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
    verified_results: dict[tuple[str, str], dict[str, object]] = {}
    for logical_path, entry in reviews.items():
        evidence = entry["evidence"]
        assert isinstance(evidence, dict)
        key = (str(evidence["artifact_locator"]), str(evidence["artifact_sha256"]))
        result = verified_results.get(key)
        if result is None:
            result = checked_critical_listening_result(ROOT / key[0])
            quality_review_bundle_contract(result)
            verify_quality_review_source_tree(result, key[0])
            verified_results[key] = result
        verify_quality_review_result(entry, evidence, logical_path, result)
    return reviews


def codec_contract(suffix: str) -> tuple[str, str, str]:
    if suffix == ".flac":
        return "flac", "flac", "ffmpeg"
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


def published_quality_review(review: dict[str, object]) -> dict[str, object]:
    evidence = review.get("evidence")
    if not isinstance(evidence, dict):
        raise ReleaseError("passed quality review lacks evidence")
    attestation_url = evidence.get("github_attestation_url")
    if not isinstance(attestation_url, str):
        raise ReleaseError("passed quality review lacks a GitHub attestation")
    published_evidence = {
        key: value for key, value in evidence.items()
        if key != "github_attestation_url"
    }
    published_evidence["notes"] = (
        f"{str(evidence.get('notes', '')).strip()} "
        f"Quality-review record SHA-256: {hashlib.sha256(canonical_json(review)).hexdigest()}; "
        f"GitHub attestation: {attestation_url}"
    )
    return {**review, "evidence": published_evidence}


def build_source_manifest(*, allow_historical_toolchain: bool = False) -> dict[str, object]:
    toolchain = checked_toolchain(allow_historical=allow_historical_toolchain)
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
    for relative, path, replacement in source_coordinates(
        allow_missing_historical_replacements=allow_historical_toolchain,
    ):
        source_relative = path.relative_to(ROOT).as_posix()
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
            "source_path": source_relative,
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
                str(replacement["transformation_notes"])
                + (
                    f" Replaces {relative} at {replacement['replaced_source_commit']} "
                    f"(SHA-256 {replacement['replaced_source_sha256']})."
                )
                if replacement is not None
                else (
                    "second lossy generation from the only preserved Vorbis source; quality review required"
                    if path.suffix.lower() == ".ogg"
                    else "rendered from the preserved authored source at release time"
                )
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
        if path.suffix.lower() == ".ogg" or replacement is not None:
            quality_review = quality_reviews.get(relative)
            if quality_review is not None and quality_review.get("source_sha256") != asset["source"]["sha256"]:  # type: ignore[index]
                raise ReleaseError(f"stale quality review: {relative}")
            asset["quality_review"] = published_quality_review(quality_review) if quality_review is not None else {
                "status": "blocked",
                "blocking_finding": (
                    "replacement source-to-Opus behavioral and critical-listening review evidence is missing"
                    if replacement is not None
                    else "second-generation Vorbis-to-Opus review evidence is missing"
                ),
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
    discovered_paths = {path.relative_to(ROOT).as_posix() for path in discovered}
    manifest_source_paths = {str(asset.get("source_path")) for asset in assets if isinstance(asset, dict)}
    if manifest_source_paths != discovered_paths:
        raise ReleaseError("source manifest paths do not exactly cover the discovered corpus")
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
        source_path = asset.get("source_path")
        if not isinstance(source_path, str):
            raise ReleaseError(f"invalid source path: {logical_path}")
        path = ROOT / source_path
        if not path.is_file() or path.is_symlink():
            raise ReleaseError(f"manifest source is not a tracked regular file: {source_path}")
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


def checked_toolchain(
    *, allow_historical: bool = False, playtest: bool = False,
    classic: bool = False,
) -> dict[str, object]:
    if playtest and classic:
        raise ReleaseError("toolchain cannot be both playtest-only and publishable Classic")
    legacy_paths = playtest or classic
    if allow_historical and legacy_paths:
        raise ReleaseError("historical toolchains are not valid for legacy-path products")
    schema_name = (
        "playtest-audio-toolchain-v1.schema.json" if playtest else
        "classic-audio-toolchain-v1.schema.json" if classic else
        "audio-toolchain-v1.schema.json"
    )
    toolchain_path = PLAYTEST_TOOLCHAIN if playtest else CLASSIC_TOOLCHAIN if classic else TOOLCHAIN
    toolchain_schema = checked_schema(schema_name)
    value = read_json(toolchain_path)
    if not isinstance(value, dict) or set(value) != {"$schema", "schema_version", "apt_snapshot", "build_image", "duration_tolerance_seconds", "quality_budget", "instrument_bank", "license_texts", "runtime_libraries", "tools"} or value.get("$schema") != f"../schemas/{schema_name}" or value.get("schema_version") != 1:
        raise ReleaseError("toolchain root must use schema version 1")
    validate_schema_instance(value, toolchain_schema)
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
    tools = value.get("tools")
    runtime_tools = {"ffmpeg", "timidity", "openmpt123", "opusenc", "opusinfo", "sdl3_mixer_probe"}
    playtest_tools = {"ffmpeg", "wildmidi", "openmpt123", "opusenc", "opusinfo", "sdl3_mixer_probe"}
    current_tools = playtest_tools if legacy_paths else runtime_tools
    historical_tools = {"ffmpeg", "timidity", "openmpt123", "opusenc", "opusinfo", "sdl3_mixer_probe"}
    allowed_tools = {frozenset(current_tools)}
    if allow_historical:
        allowed_tools.add(frozenset(historical_tools))
    if not isinstance(tools, dict) or frozenset(tools) not in allowed_tools:
        raise ReleaseError(f"toolchain must define exactly: {', '.join(sorted(current_tools))}")
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
            source_path = contract.get("source_path")
            source_sha256 = contract.get("source_sha256")
            if (source_path is None) != (source_sha256 is None):
                raise ReleaseError(f"tool source contract is incomplete: {name}")
            if isinstance(source_path, str):
                source = ROOT / source_path
                if not source.is_file() or sha256(source) != source_sha256:
                    raise ReleaseError(f"tool source does not match its pinned SHA-256: {name}")
    probe = tools["sdl3_mixer_probe"]
    assert isinstance(probe, dict)
    probe_source = probe.get("source_path")
    probe_sha256 = probe.get("source_sha256")
    probe_installed = probe.get("installed_path")
    probe_installed_sha256 = probe.get("installed_sha256")
    if (
        not isinstance(probe_source, str)
        or not isinstance(probe_sha256, str)
        or ((probe_installed is None) != (probe_installed_sha256 is None))
        or (
            probe_installed is not None
            and (
                not isinstance(probe_installed, str)
                or not probe_installed.startswith("/")
                or not re.fullmatch(r"[0-9a-f]{64}", str(probe_installed_sha256 or ""))
            )
        )
        or (legacy_paths and probe_installed is None)
    ):
        raise ReleaseError("SDL3_mixer probe must pin its source and installed binary")
    probe_path = ROOT / probe_source
    if not probe_path.is_file() or sha256(probe_path) != probe_sha256:
        raise ReleaseError("SDL3_mixer probe source does not match its pinned SHA-256")
    timidity = tools.get("timidity")
    deterministic_seed = timidity.get("deterministic_seed") if isinstance(timidity, dict) else None
    if isinstance(deterministic_seed, dict):
        seed_source = ROOT / str(deterministic_seed["source_path"])
        if not seed_source.is_file() or sha256(seed_source) != deterministic_seed["source_sha256"]:
            raise ReleaseError("TiMidity deterministic seed source does not match its pinned SHA-256")
    if allow_historical:
        # Historical review trees were already validated by their own pinned
        # Dockerfile contract. Reconstruct their canonical source manifest with
        # the version-1 tool shape, without applying today's stronger image pins.
        return value
    dockerfile_name = (
        "playtest.Dockerfile" if playtest else
        "classic-runtime.Dockerfile" if classic else "Dockerfile"
    )
    dockerfile = (ROOT / "tools" / "audio" / dockerfile_name).read_text(encoding="utf-8")
    docker_pinned_tools = {"ffmpeg", "openmpt123", "opusenc"}
    if legacy_paths:
        docker_pinned_tools.add("wildmidi")
    required_literals = [
        str(build_image["image"]),
        str(value["apt_snapshot"]),
        str(debian_source["url"]), str(debian_source["sha256"]), str(bank["upstream_archive_sha256"]),
        *(str(contract[field]) for contract in license_texts.values() if str(contract["installed_path"]).startswith("/opt/") for field in ("source_url", "sha256")),
        *(str(contract["package"]).split("=", 1)[1] for name, contract in tools.items() if name in docker_pinned_tools),
        *(
            str(contract[field]) for name, contract in tools.items()
            if name != "sdl3_mixer_probe" and isinstance(contract, dict) and isinstance(contract.get("source_path"), str)
            for field in ("source_path", "source_sha256", "installed_path", "installed_sha256")
        ),
        *([str(probe_installed), str(probe_installed_sha256)] if probe_installed is not None else []),
        *(
            [str(deterministic_seed["installed_path"]), str(deterministic_seed["installed_sha256"])]
            if isinstance(deterministic_seed, dict) else []
        ),
    ]
    if any(literal not in dockerfile for literal in required_literals):
        raise ReleaseError("Dockerfile drifts from pinned toolchain coordinates")
    return value


def checked_playtest_toolchain() -> dict[str, object]:
    return checked_toolchain(playtest=True)


def checked_classic_toolchain() -> dict[str, object]:
    classic = checked_toolchain(classic=True)
    playtest = checked_toolchain(playtest=True)
    normalized_classic = {**classic, "$schema": playtest["$schema"]}
    if canonical_json(normalized_classic) != canonical_json(playtest):
        raise ReleaseError("Classic and playtest legacy-path recipes have drifted")
    if (
        ROOT / "tools" / "audio" / "classic-runtime.Dockerfile"
    ).read_bytes() != (
        ROOT / "tools" / "audio" / "playtest.Dockerfile"
    ).read_bytes():
        raise ReleaseError("Classic and playtest legacy-path build images have drifted")
    return classic


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


def validate_playtest_manifest(manifest: dict[str, object]) -> None:
    schema = checked_schema("playtest-manifest-v1.schema.json")
    required = {
        "$schema", "schema_version", "playtest_only", "publishable",
        "source_commit", "source_tree", "source_manifest_sha256",
        "toolchain_sha256", "tool_versions", "schema_sha256", "marker_sha256",
        "blocker_report_sha256", "blocker_count", "logical_path_count",
        "copied_vorbis_count", "converted_opus_count", "output_tree_sha256",
        "assets",
    }
    if (
        set(manifest) != required
        or manifest.get("$schema") != "schemas/playtest-manifest-v1.schema.json"
        or manifest.get("schema_version") != 1
        or manifest.get("playtest_only") is not True
        or manifest.get("publishable") is not False
    ):
        raise ReleaseError("playtest manifest does not satisfy the version 1 schema")
    validate_schema_instance(manifest, schema)
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ReleaseError("playtest manifest must contain assets")
    logical_paths: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ReleaseError("playtest manifest asset must be an object")
        logical_path = asset.get("logical_path")
        if not isinstance(logical_path, str) or logical_path in logical_paths:
            raise ReleaseError("playtest manifest logical paths must be unique")
        logical_paths.add(logical_path)
        source = asset.get("source")
        output = asset.get("output")
        mode = asset.get("mapping")
        if not isinstance(source, dict) or not isinstance(output, dict):
            raise ReleaseError(f"playtest asset metadata is incomplete: {logical_path}")
        expected = (
            ("copy", "vorbis", "vorbis")
            if source.get("codec") == "vorbis"
            else ("render-opus", source.get("codec"), "opus")
        )
        if (mode, source.get("codec"), output.get("codec")) != expected:
            raise ReleaseError(f"playtest asset has a nondeterministic codec mapping: {logical_path}")
        if mode == "copy" and source.get("sha256") != output.get("sha256"):
            raise ReleaseError(f"copied Vorbis payload hash differs from its source: {logical_path}")
    if manifest.get("logical_path_count") != len(assets):
        raise ReleaseError("playtest logical-path count does not match its assets")
    copied = sum(asset.get("mapping") == "copy" for asset in assets if isinstance(asset, dict))
    converted = sum(asset.get("mapping") == "render-opus" for asset in assets if isinstance(asset, dict))
    if manifest.get("copied_vorbis_count") != copied or manifest.get("converted_opus_count") != converted:
        raise ReleaseError("playtest codec counts do not match its assets")


def validate_classic_runtime_manifest(manifest: dict[str, object]) -> None:
    schema = checked_schema(CLASSIC_RUNTIME_SCHEMA_NAME)
    required = {
        "$schema", "schema_version", "publishable", "playtest_only",
        "release_tag", "source_commit", "source_tree",
        "source_manifest_sha256", "toolchain_sha256", "tool_versions",
        "schema_sha256", "remediation_report_sha256",
        "remediation_finding_count", "logical_path_count",
        "copied_vorbis_count", "converted_opus_count",
        "output_tree_sha256", "assets",
    }
    if (
        set(manifest) != required
        or manifest.get("$schema") != f"schemas/{CLASSIC_RUNTIME_SCHEMA_NAME}"
        or manifest.get("schema_version") != 1
        or manifest.get("publishable") is not True
        or manifest.get("playtest_only") is not False
    ):
        raise ReleaseError("Classic runtime manifest does not satisfy the version 1 schema")
    validate_schema_instance(manifest, schema)
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ReleaseError("Classic runtime manifest must contain assets")
    logical_paths: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ReleaseError("Classic runtime manifest asset must be an object")
        logical_path = asset.get("logical_path")
        if not isinstance(logical_path, str) or logical_path in logical_paths:
            raise ReleaseError("Classic runtime logical paths must be unique")
        logical_paths.add(logical_path)
        source = asset.get("source")
        output = asset.get("output")
        mapping = asset.get("mapping")
        if not isinstance(source, dict) or not isinstance(output, dict):
            raise ReleaseError(f"Classic runtime asset metadata is incomplete: {logical_path}")
        expected = (
            ("copy", "vorbis", "vorbis")
            if source.get("codec") == "vorbis"
            else ("render-opus", source.get("codec"), "opus")
        )
        if (mapping, source.get("codec"), output.get("codec")) != expected:
            raise ReleaseError(f"Classic runtime asset has an invalid codec mapping: {logical_path}")
        if mapping == "copy" and source.get("sha256") != output.get("sha256"):
            raise ReleaseError(f"copied Classic Vorbis hash differs from its source: {logical_path}")
    copied = sum(asset.get("mapping") == "copy" for asset in assets if isinstance(asset, dict))
    converted = sum(asset.get("mapping") == "render-opus" for asset in assets if isinstance(asset, dict))
    if manifest.get("logical_path_count") != len(assets):
        raise ReleaseError("Classic runtime logical-path count does not match its assets")
    if manifest.get("copied_vorbis_count") != copied or manifest.get("converted_opus_count") != converted:
        raise ReleaseError("Classic runtime codec counts do not match its assets")


def run(
    command: list[str],
    *,
    capture: bool = False,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            cwd=cwd,
            env=env,
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


def verify_toolchain(
    toolchain: dict[str, object], *, strict_playtest: bool = False,
) -> dict[str, str]:
    if strict_playtest:
        forbidden_names = {"ATRINIK_INSTRUMENT_CONFIG", "DPKG_ADMINDIR", "DPKG_ROOT"}
        forbidden_prefixes = ("GLIBC_", "LD_", "MALLOC_")
        for name, value in os.environ.items():
            if value and (name in forbidden_names or name.startswith(forbidden_prefixes)):
                raise ReleaseError(f"pinned toolchain rejects environment override: {name}")
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
        installed_path = contract.get("installed_path")
        installed_sha256 = contract.get("installed_sha256")
        installed = Path(installed_path) if isinstance(installed_path, str) else None
        if strict_playtest:
            if installed is None:
                raise ReleaseError(f"required tool is not the pinned executable: {name}")
            command_path = Path(command[0])
            if command_path.is_absolute():
                expected_executable = command_path.resolve()
            elif command_path.name == installed.name:
                expected_executable = installed.resolve()
            else:
                raise ReleaseError(f"required tool is not the pinned executable: {name}")
            if Path(executable).resolve() != expected_executable:
                raise ReleaseError(f"required tool is not the pinned executable: {name}")
        version_command = list(command)
        if strict_playtest and installed is not None and Path(version_command[0]).name == installed.name:
            version_command[0] = str(installed)
        completed = run(version_command, capture=True)
        output = (completed.stdout + completed.stderr).strip()
        if not re.search(expected, output, re.MULTILINE):
            raise ReleaseError(f"unexpected {name} version; expected /{expected}/, got: {output}")
        versions[name] = output.splitlines()[0]
        if name != "sdl3_mixer_probe" or installed is not None:
            if installed is None or not isinstance(installed_sha256, str):
                raise ReleaseError(f"tool lacks an installed binary hash: {name}")
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


def render_source(
    asset: dict[str, object],
    output: Path,
    toolchain: dict[str, object],
    *,
    source_root: Path | None = None,
    command_root: Path | None = None,
) -> None:
    source = (ROOT if source_root is None else source_root) / str(asset["source_path"])
    render = asset["render"]
    assert isinstance(render, dict)
    renderer = render["renderer"]
    recipe = render.get("recipe")
    if not isinstance(recipe, list) or not all(isinstance(part, str) for part in recipe):
        raise ReleaseError(f"invalid render recipe for {asset['logical_path']}")
    command_source = source.relative_to(command_root) if command_root is not None else source
    command_output = output.relative_to(command_root) if command_root is not None else output
    replacements = {"{input}": str(command_source), "{output}": str(command_output)}
    if renderer in {"wildmidi", "timidity"}:
        bank = toolchain["instrument_bank"]
        assert isinstance(bank, dict)
        config_path = Path(
            str(bank["installed_config"])
            if command_root is not None
            else os.environ.get("ATRINIK_INSTRUMENT_CONFIG", str(bank["installed_config"]))
        )
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
    if command_root is not None:
        renderer_contract = toolchain["tools"][renderer]  # type: ignore[index]
        assert isinstance(renderer_contract, dict)
        command[0] = str(renderer_contract["installed_path"])
    run(command, cwd=command_root)


def encode_opus(
    asset: dict[str, object],
    wave_path: Path,
    opus_path: Path,
    toolchain: dict[str, object],
    *,
    command_root: Path | None = None,
) -> None:
    encode = asset["encode"]
    assert isinstance(encode, dict)
    serial = int(str(asset["source"]["sha256"])[0:8], 16)  # type: ignore[index]
    command = [
        (
            str(toolchain["tools"]["opusenc"]["installed_path"])  # type: ignore[index]
            if command_root is not None else "opusenc"
        ),
        "--quiet",
        "--bitrate", str(encode["bitrate_kbps"]),
        f"--{encode['mode']}",
        "--comp", str(encode["complexity"]),
        "--serial", str(serial),
        "--discard-comments",
    ]
    if encode["signal"] == "music":
        command.append("--music")
    command_wave = wave_path.relative_to(command_root) if command_root is not None else wave_path
    command_opus = opus_path.relative_to(command_root) if command_root is not None else opus_path
    command.extend([str(command_wave), str(command_opus)])
    run(command, cwd=command_root)


def run_sdl_probe(
    path: Path,
    *,
    expected_frames: int,
    behaviors: tuple[str, ...],
    expected_channels: int,
    toolchain: dict[str, object],
    strict_playtest: bool = False,
) -> None:
    probe = toolchain["tools"]["sdl3_mixer_probe"]  # type: ignore[index]
    assert isinstance(probe, dict)
    probe_command = probe["decode_command"]
    assert isinstance(probe_command, list)
    replacements = {
        "{input}": str(path),
        "{expected_frames}": str(expected_frames),
        "{behaviors}": ",".join(behaviors) or "none",
        "{expected_channels}": str(expected_channels),
    }
    command = [str(part) for part in probe_command]
    for placeholder, value in replacements.items():
        command = [part.replace(placeholder, value) for part in command]
    if strict_playtest:
        command[0] = str(probe["installed_path"])
    run(command)


def validate_conversion_durations(
    asset: dict[str, object],
    rendered_duration: float,
    decoded_duration: float,
    tolerance: float,
) -> None:
    if abs(decoded_duration - rendered_duration) > 0.1:
        raise ReleaseError(f"Opus output has a truncated or extended tail for {asset['logical_path']}")
    render = asset["render"]
    source = asset["source"]
    assert isinstance(render, dict) and isinstance(source, dict)
    source_duration = float(source["duration_seconds"])
    if render["renderer"] != "wildmidi" and abs(decoded_duration - source_duration) > tolerance:
        raise ReleaseError(
            f"duration outside {tolerance}s tolerance for {asset['logical_path']}: "
            f"source={source_duration}, decoded={decoded_duration}"
        )


def convert_asset(
    asset: dict[str, object],
    output_root: Path,
    toolchain: dict[str, object],
    behaviors: tuple[str, ...] = (),
    *,
    source_root: Path | None = None,
) -> dict[str, object]:
    generated = output_root / str(asset["generated_path"])
    generated.parent.mkdir(parents=True, exist_ok=True)
    strict_playtest = source_root is not None
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-") as temporary:
        temporary_path = Path(temporary)
        input_root = ROOT
        if strict_playtest:
            input_root = temporary_path / "source"
            stable_source = input_root / str(asset["source_path"])
            stable_source.parent.mkdir(parents=True, exist_ok=True)
            original_source = source_root / str(asset["source_path"])
            shutil.copyfile(original_source, stable_source)
            if sha256(stable_source) != asset["source"]["sha256"]:  # type: ignore[index]
                raise ReleaseError(f"source changed before conversion: {asset['logical_path']}")
        rendered_wave = temporary_path / "rendered.wav"
        decoded_wave = temporary_path / "decoded.wav"
        encoded_opus = temporary_path / "generated.opus" if strict_playtest else generated
        render_source(
            asset,
            rendered_wave,
            toolchain,
            source_root=input_root if strict_playtest else None,
            command_root=temporary_path if strict_playtest else None,
        )
        quality_budget = toolchain["quality_budget"]
        assert isinstance(quality_budget, dict)
        rendered = attenuate_clipped_wave(
            rendered_wave,
            float(quality_budget["clipped_render_peak_target_dbfs"]),
        )
        encode_opus(
            asset, rendered_wave, encoded_opus, toolchain,
            command_root=temporary_path if strict_playtest else None,
        )
        opusinfo = str(toolchain["tools"]["opusinfo"]["installed_path"]) if strict_playtest else "opusinfo"  # type: ignore[index]
        ffmpeg = str(toolchain["tools"]["ffmpeg"]["installed_path"]) if strict_playtest else "ffmpeg"  # type: ignore[index]
        run([opusinfo, "-q", str(encoded_opus)])
        run([ffmpeg, "-nostdin", "-v", "error", "-i", str(encoded_opus), "-map_metadata", "-1", "-c:a", "pcm_s16le", "-y", str(decoded_wave)])
        decoded = inspect_wave(decoded_wave)
        if decoded["clipping"]:
            raise ReleaseError(f"decoded Opus PCM clips for {asset['logical_path']}")
        run_sdl_probe(
            encoded_opus,
            expected_frames=round(float(decoded["duration_seconds"]) * int(quality_budget["sample_rate"])),
            behaviors=behaviors,
            expected_channels=int(asset["render"]["channels"]),  # type: ignore[index]
            toolchain=toolchain,
            strict_playtest=strict_playtest,
        )
        if strict_playtest:
            shutil.move(encoded_opus, generated)
    intended_channels = int(asset["render"]["channels"])  # type: ignore[index]
    expected_rate = int(toolchain["quality_budget"]["sample_rate"])  # type: ignore[index]
    if rendered["sample_rate"] != expected_rate or decoded["sample_rate"] != expected_rate:
        raise ReleaseError(f"unexpected output sample rate for {asset['logical_path']}")
    if rendered["channels"] != intended_channels or decoded["channels"] != intended_channels:
        raise ReleaseError(f"unexpected output channel count for {asset['logical_path']}")
    tolerance = float(toolchain["duration_tolerance_seconds"])
    validate_conversion_durations(
        asset,
        float(rendered["duration_seconds"]),
        float(decoded["duration_seconds"]),
        tolerance,
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


def blocker_report(manifest: dict[str, object], blockers: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "source_count": manifest["audio_source_count"],
        "count": len(blockers),
        "findings": blockers,
    }


def classic_release_notes(blockers: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for finding in blockers:
        category = str(finding.get("category", "unknown"))
        counts[category] = counts.get(category, 0) + 1
    if not blockers:
        status = "No Classic restoration modernization findings remain."
    else:
        labels = {
            "license/provenance": "license/provenance",
            "quality-review": "formal quality-review",
        }
        details = " and ".join(
            f"**{count} {labels.get(category, category)}**"
            for category, count in sorted(counts.items())
        )
        status = (
            "The Classic restoration runtime republishes Atrinik's existing corpus; "
            f"it does not newly clear {details} findings (**{len(blockers)} total**)."
        )
    return (
        "### Classic restoration modernization status\n\n"
        f"{status} Track the separate modernization work in "
        "[atrinik/sound#31](https://github.com/atrinik/sound/issues/31).\n"
    )


def legacy_path_assets(
    source_manifest: dict[str, object], toolchain: dict[str, object],
) -> list[dict[str, object]]:
    """Overlay the deterministic legacy-path MIDI recipe without changing sources."""
    source_assets = source_manifest.get("assets")
    if not isinstance(source_assets, list):
        raise ReleaseError("source manifest assets must be an array")
    sample_rate = int(toolchain["quality_budget"]["sample_rate"])  # type: ignore[index]
    assets = copy.deepcopy(source_assets)
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("source"), dict):
            raise ReleaseError("source manifest asset is incomplete")
        if asset["source"].get("codec") != "midi":  # type: ignore[union-attr]
            continue
        render = asset.get("render")
        if not isinstance(render, dict) or render.get("renderer") != "timidity":
            raise ReleaseError(f"runtime MIDI recipe drifted: {asset.get('logical_path')}")
        asset["render"] = {
            **render,
            "renderer": "wildmidi",
            "recipe": [
                "wildmidi", "-c", "{instrument_config}",
                "-r", str(sample_rate), "-o", "{output}", "{input}",
            ],
        }
    return assets


def playtest_assets(
    source_manifest: dict[str, object], toolchain: dict[str, object],
) -> list[dict[str, object]]:
    """Return assets for the explicitly nonpublishing local playtest tree."""
    return legacy_path_assets(source_manifest, toolchain)


def playtest_output_record(
    asset: dict[str, object], output: Path, *, codec: str, container: str,
    sample_rate: int, channels: int, duration_seconds: float,
) -> dict[str, object]:
    source = asset["source"]
    assert isinstance(source, dict)
    return {
        "logical_path": asset["logical_path"],
        "source_path": asset["source_path"],
        "mapping": "copy" if codec == "vorbis" else "render-opus",
        "source": {
            "sha256": source["sha256"],
            "codec": source["codec"],
            "container": source["container"],
        },
        "output": {
            "sha256": sha256(output),
            "size_bytes": output.stat().st_size,
            "codec": codec,
            "container": container,
            "sample_rate": sample_rate,
            "channels": channels,
            "duration_seconds": duration_seconds,
        },
    }


def convert_legacy_asset(
    asset: dict[str, object],
    output_root: Path,
    toolchain: dict[str, object],
) -> dict[str, object]:
    """Convert from a private, hash-bound copy of exactly one authored source."""
    source = asset["source"]
    assert isinstance(source, dict)
    expected_hash = str(source["sha256"])
    source_path = PurePosixPath(str(asset["source_path"]))
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-playtest-source-") as temporary:
        snapshot_root = Path(temporary)
        snapshot = snapshot_root / source_path
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source_path, snapshot)
        if sha256(snapshot) != expected_hash:
            raise ReleaseError(f"legacy-path source changed while snapshotting: {source_path}")
        converted = convert_asset(
            asset,
            output_root,
            toolchain,
            source_root=snapshot_root,
        )
        if sha256(snapshot) != expected_hash:
            raise ReleaseError(f"legacy-path source snapshot changed during conversion: {source_path}")
    return converted


def convert_playtest_asset(
    asset: dict[str, object],
    output_root: Path,
    toolchain: dict[str, object],
) -> dict[str, object]:
    """Convert one asset for the explicitly nonpublishing local playtest tree."""
    return convert_legacy_asset(asset, output_root, toolchain)


@contextlib.contextmanager
def playtest_root_lock(_output: Path) -> Iterator[None]:
    """Hold the Git-admin reader lease shared with wrapper worktree cleanup."""
    try:
        environment = exact_git_environment()
        require_selected_git_worktree(environment)
        raw_lock = run(
            [
                "git",
                "-C",
                str(ROOT),
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                PLAYTEST_ROOT_LOCK_NAME,
            ],
            capture=True,
            env=environment,
        ).stdout.strip()
    except (ReleaseError, SourceIntegrityError) as exc:
        raise ReleaseError("playtest root lock requires Git worktree metadata") from exc
    lock = Path(raw_lock)
    if not raw_lock or not lock.is_absolute() or not lock.parent.is_dir():
        raise ReleaseError("playtest root lock path is invalid")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise ReleaseError(f"playtest root lock is not a safe regular file: {lock}") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise ReleaseError(f"playtest root lock is not a safe regular file: {lock}")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReleaseError(f"playtest cache root is being removed: {lock}") from exc
        os.lseek(descriptor, 0, os.SEEK_SET)
        marker = os.read(descriptor, len(PLAYTEST_ROOT_LOCK_MARKER) + 1)
        if not marker:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ReleaseError(f"playtest root lock is being initialized: {lock}") from exc
            os.lseek(descriptor, 0, os.SEEK_SET)
            marker = os.read(descriptor, len(PLAYTEST_ROOT_LOCK_MARKER) + 1)
            if not marker:
                os.ftruncate(descriptor, 0)
                os.write(descriptor, PLAYTEST_ROOT_LOCK_MARKER)
                os.fsync(descriptor)
                marker = PLAYTEST_ROOT_LOCK_MARKER
            fcntl.flock(descriptor, fcntl.LOCK_SH)
        if marker != PLAYTEST_ROOT_LOCK_MARKER:
            raise ReleaseError(f"playtest root lock has an invalid marker: {lock}")
        yield
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def playtest_output_lock(output: Path) -> Iterator[None]:
    lock = output.parent / f".{output.name}.build.lock"
    with playtest_root_lock(output):
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            raise ReleaseError(f"playtest output lock is not a safe regular file: {lock}") from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
            ):
                raise ReleaseError(f"playtest output lock is not a safe regular file: {lock}")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ReleaseError(f"playtest output has an active build lock: {lock}") from exc
            os.fchmod(descriptor, 0o600)
            os.ftruncate(descriptor, 0)
            os.write(descriptor, b"atrinik-sound-playtest-tree-v1\n")
            os.fsync(descriptor)
            yield
        finally:
            os.close(descriptor)


@contextlib.contextmanager
def playtest_verification_lock(output: Path) -> Iterator[None]:
    """Hold both leases needed to keep one verified output present."""
    lock = output.parent / f".{output.name}.build.lock"
    with playtest_root_lock(output):
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            raise ReleaseError(f"playtest output lock is not a safe regular file: {lock}") from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
            ):
                raise ReleaseError(f"playtest output lock is not a safe regular file: {lock}")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ReleaseError(f"playtest output is being removed: {lock}") from exc
            yield
        finally:
            os.close(descriptor)


def _playtest_files(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        mode = path.stat(follow_symlinks=False).st_mode
        if stat.S_ISLNK(mode):
            raise ReleaseError(f"playtest tree contains a symlink: {path.relative_to(root)}")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ReleaseError(f"playtest tree contains a non-regular entry: {path.relative_to(root)}")
        files.add(path.relative_to(root).as_posix())
    return files


def _open_regular_beneath(root_descriptor: int, relative: str) -> int:
    """Open a regular file beneath a retained root without following symlinks."""
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
        raise ReleaseError(f"unsafe playtest-tree path: {relative}")
    directory = os.dup(root_descriptor)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise ReleaseError(f"playtest tree contains a non-regular entry: {relative}")
        return descriptor
    except OSError as exc:
        raise ReleaseError(f"playtest tree changed or contains a symlink: {relative}") from exc
    finally:
        os.close(directory)


def start_playtest_mutation_watch(root: Path) -> tuple[int, int]:
    """Watch every existing tree entry for writes or namespace mutations."""
    library = ctypes.CDLL(None, use_errno=True)
    try:
        initialize = library.inotify_init1
        add_watch = library.inotify_add_watch
    except AttributeError as exc:
        raise ReleaseError("playtest mutation monitoring is unavailable") from exc
    initialize.argtypes = [ctypes.c_int]
    initialize.restype = ctypes.c_int
    add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    add_watch.restype = ctypes.c_int
    descriptor = initialize(os.O_CLOEXEC | os.O_NONBLOCK)
    if descriptor < 0:
        error = ctypes.get_errno()
        raise ReleaseError(f"cannot initialize playtest mutation monitoring: {os.strerror(error)}")
    mutation_mask = (
        0x00000002  # IN_MODIFY
        | 0x00000004  # IN_ATTRIB
        | 0x00000008  # IN_CLOSE_WRITE
        | 0x00000040  # IN_MOVED_FROM
        | 0x00000080  # IN_MOVED_TO
        | 0x00000100  # IN_CREATE
        | 0x00000200  # IN_DELETE
        | 0x00000400  # IN_DELETE_SELF
        | 0x00000800  # IN_MOVE_SELF
        | 0x00002000  # IN_UNMOUNT
        | 0x02000000  # IN_DONT_FOLLOW
    )
    try:
        root_directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        os.close(descriptor)
        raise ReleaseError(f"cannot anchor playtest mutation monitoring: {root}") from exc
    try:
        def watch(path: str, label: str) -> int:
            watch_descriptor = add_watch(descriptor, os.fsencode(path), mutation_mask)
            if watch_descriptor < 0:
                error = ctypes.get_errno()
                raise ReleaseError(
                    f"cannot monitor playtest tree entry {label}: {os.strerror(error)}"
                )
            return watch_descriptor
        def watch_tree(directory_descriptor: int, label: PurePosixPath) -> int:
            directory_watch = watch(
                f"/proc/self/fd/{directory_descriptor}/.", label.as_posix(),
            )
            try:
                entries = list(os.scandir(directory_descriptor))
            except OSError as exc:
                raise ReleaseError(f"cannot enumerate playtest tree for mutation monitoring: {label}") from exc
            for entry in entries:
                child_label = label / entry.name
                if entry.is_dir(follow_symlinks=False):
                    try:
                        child = os.open(
                            entry.name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory_descriptor,
                        )
                    except OSError as exc:
                        raise ReleaseError(
                            f"playtest tree changed while monitoring: {child_label}"
                        ) from exc
                    try:
                        watch_tree(child, child_label)
                    finally:
                        os.close(child)
                else:
                    watch(
                        f"/proc/self/fd/{directory_descriptor}/{entry.name}",
                        child_label.as_posix(),
                    )
            return directory_watch

        root_watch_descriptor = watch_tree(root_directory, PurePosixPath("."))
        reject_playtest_mutations(descriptor)
        return descriptor, root_watch_descriptor
    except Exception:
        os.close(descriptor)
        raise
    finally:
        os.close(root_directory)


def reject_playtest_mutations(
    descriptor: int, *, allowed_root_move_watch: int | None = None,
) -> None:
    """Drain the inotify queue at the verification linearization point."""
    try:
        events = os.read(descriptor, 1024 * 1024)
    except BlockingIOError:
        return
    offset = 0
    while offset < len(events):
        watch_descriptor, mask, _cookie, name_length = struct.unpack_from(
            "iIII", events, offset,
        )
        offset += 16 + name_length
        if (
            allowed_root_move_watch is not None
            and watch_descriptor == allowed_root_move_watch
            and mask == 0x00000800  # IN_MOVE_SELF from the intentional install
        ):
            continue
        raise ReleaseError("playtest tree changed during verification")


@contextlib.contextmanager
def stable_playtest_snapshot(
    root: Path, *, root_location: list[Path] | None = None,
) -> Iterator[PlaytestSnapshotGuard]:
    """Copy a tree from retained no-follow fds and reject concurrent replacement."""
    try:
        root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ReleaseError(f"playtest tree is not a safe directory: {root}") from exc
    original_root = os.fstat(root_descriptor)
    try:
        mutation_descriptor, root_watch_descriptor = start_playtest_mutation_watch(root)
    except Exception:
        os.close(root_descriptor)
        raise
    descriptors: dict[str, tuple[int, os.stat_result, str]] = {}
    try:
        files = _playtest_files(root)
        with tempfile.TemporaryDirectory(prefix="atrinik-sound-playtest-verify-tree-") as temporary:
            snapshot = Path(temporary)
            for relative in sorted(files):
                descriptor = _open_regular_beneath(root_descriptor, relative)
                metadata = os.fstat(descriptor)
                destination = snapshot / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with os.fdopen(os.dup(descriptor), "rb") as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                descriptors[relative] = (descriptor, metadata, sha256(destination))
            yield PlaytestSnapshotGuard(
                snapshot, mutation_descriptor, root_watch_descriptor,
            )
            current_root_path = root if root_location is None else root_location[0]
            try:
                current_files = _playtest_files(current_root_path)
            except OSError as exc:
                raise ReleaseError("playtest tree changed during verification") from exc
            if current_files != files:
                raise ReleaseError("playtest tree changed during verification")
            for relative, (descriptor, original, expected_sha256) in descriptors.items():
                current_descriptor = _open_regular_beneath(root_descriptor, relative)
                try:
                    current = os.fstat(current_descriptor)
                finally:
                    os.close(current_descriptor)
                retained = os.fstat(descriptor)
                identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
                if identity(current) != identity(original) or identity(retained) != identity(original):
                    raise ReleaseError(f"playtest tree changed during verification: {relative}")
                os.lseek(descriptor, 0, os.SEEK_SET)
                with os.fdopen(os.dup(descriptor), "rb") as retained_file:
                    retained_sha256 = hashlib.file_digest(retained_file, "sha256").hexdigest()
                if retained_sha256 != expected_sha256:
                    raise ReleaseError(f"playtest tree changed during verification: {relative}")
            try:
                current_root = os.stat(current_root_path, follow_symlinks=False)
            except OSError as exc:
                raise ReleaseError("playtest tree root changed during verification") from exc
            if (
                not stat.S_ISDIR(current_root.st_mode)
                or (current_root.st_dev, current_root.st_ino)
                != (original_root.st_dev, original_root.st_ino)
            ):
                raise ReleaseError("playtest tree root changed during verification")
            reject_playtest_mutations(
                mutation_descriptor,
                allowed_root_move_watch=(
                    root_watch_descriptor if current_root_path != root else None
                ),
            )
    finally:
        for descriptor, _metadata, _digest in descriptors.values():
            os.close(descriptor)
        os.close(root_descriptor)
        os.close(mutation_descriptor)


def verify_playtest_tree(
    root: Path,
    *,
    require_build_path: bool = True,
    mode: PlaytestVerificationMode = PlaytestVerificationMode.EXISTING_TREE,
    _trusted_snapshot: bool = False,
) -> dict[str, object]:
    if mode.trusted_snapshot_only and not _trusted_snapshot:
        raise ReleaseError("built-tree verification requires the retained trusted snapshot")
    if not _trusted_snapshot:
        if require_build_path:
            with anchored_playtest_output(root, create_parents=False) as (anchored, _lexical):
                with stable_playtest_snapshot(anchored) as snapshot:
                    return verify_playtest_tree(
                        snapshot.path,
                        require_build_path=False,
                        mode=mode,
                        _trusted_snapshot=True,
                    )
        with stable_playtest_snapshot(root) as snapshot:
            return verify_playtest_tree(
                snapshot.path,
                require_build_path=False,
                mode=mode,
                _trusted_snapshot=True,
            )
    root = root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise ReleaseError(f"playtest tree is not a regular directory: {root}")
    source_commit, source_tree = clean_source_coordinates()
    source_manifest = checked_manifest()
    blockers = validate_manifest(source_manifest, verify_tracked=True)
    toolchain = checked_playtest_toolchain()
    versions = verify_toolchain(toolchain, strict_playtest=True)

    manifest_path = root / PLAYTEST_MANIFEST_NAME
    manifest_payload = manifest_path.read_bytes() if manifest_path.is_file() else b""
    manifest_value = read_json(manifest_path)
    if not isinstance(manifest_value, dict):
        raise ReleaseError("playtest manifest root must be an object")
    if manifest_payload != canonical_json(manifest_value):
        raise ReleaseError("playtest manifest is not canonical JSON")
    validate_playtest_manifest(manifest_value)
    expected_coordinates = {
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "toolchain_sha256": sha256(PLAYTEST_TOOLCHAIN),
        "schema_sha256": sha256(SCHEMA_ROOT / "playtest-manifest-v1.schema.json"),
        "tool_versions": versions,
    }
    for key, expected in expected_coordinates.items():
        if manifest_value.get(key) != expected:
            raise ReleaseError(f"playtest manifest has stale or tampered {key}")
    packaged_schema = root / "schemas" / "playtest-manifest-v1.schema.json"
    if not packaged_schema.is_file() or sha256(packaged_schema) != manifest_value["schema_sha256"]:
        raise ReleaseError("playtest manifest schema is missing or tampered")

    marker_path = root / PLAYTEST_MARKER_NAME
    expected_marker = canonical_json(PLAYTEST_MARKER)
    if not marker_path.is_file() or marker_path.read_bytes() != expected_marker:
        raise ReleaseError("playtest-only ownership marker is missing or tampered")
    if manifest_value.get("marker_sha256") != hashlib.sha256(expected_marker).hexdigest():
        raise ReleaseError("playtest marker hash does not match the manifest")

    blockers_path = root / PLAYTEST_BLOCKERS_NAME
    expected_blockers = canonical_json(blocker_report(source_manifest, blockers))
    if not blockers_path.is_file() or blockers_path.read_bytes() != expected_blockers:
        raise ReleaseError("playtest blocker report is missing, stale, or tampered")
    if manifest_value.get("blocker_report_sha256") != hashlib.sha256(expected_blockers).hexdigest():
        raise ReleaseError("playtest blocker-report hash does not match the manifest")
    if manifest_value.get("blocker_count") != len(blockers):
        raise ReleaseError("playtest blocker count does not match the source manifest")

    source_assets = playtest_assets(source_manifest, toolchain)
    actual_playtest_assets = manifest_value.get("assets")
    assert isinstance(actual_playtest_assets, list)
    expected_by_path = {str(asset["logical_path"]): asset for asset in source_assets if isinstance(asset, dict)}
    actual_by_path = {str(asset["logical_path"]): asset for asset in actual_playtest_assets if isinstance(asset, dict)}
    if set(actual_by_path) != set(expected_by_path) or len(actual_by_path) != len(actual_playtest_assets):
        raise ReleaseError("playtest tree does not close exactly over source logical paths")
    allowed_files = set(expected_by_path) | {
        PLAYTEST_MANIFEST_NAME, PLAYTEST_BLOCKERS_NAME, PLAYTEST_MARKER_NAME,
        "schemas/playtest-manifest-v1.schema.json",
    }
    if _playtest_files(root) != allowed_files:
        raise ReleaseError("playtest tree has missing or unexpected files")

    for logical_path in sorted(expected_by_path):
        source_asset = expected_by_path[logical_path]
        actual = actual_by_path[logical_path]
        source = source_asset["source"]
        render = source_asset["render"]
        output = actual.get("output")
        assert isinstance(source, dict) and isinstance(render, dict) and isinstance(output, dict)
        expected_static = {
            "logical_path": logical_path,
            "source_path": source_asset["source_path"],
            "mapping": "copy" if source["codec"] == "vorbis" else "render-opus",
            "source": {
                "sha256": source["sha256"],
                "codec": source["codec"],
                "container": source["container"],
            },
        }
        if {key: actual.get(key) for key in expected_static} != expected_static:
            raise ReleaseError(f"playtest mapping is stale or tampered: {logical_path}")
        payload = root / logical_path
        if sha256(payload) != output.get("sha256") or payload.stat().st_size != output.get("size_bytes"):
            raise ReleaseError(f"playtest payload hash or size mismatch: {logical_path}")
        if source["codec"] == "vorbis":
            expected_output = playtest_output_record(
                source_asset,
                ROOT / str(source_asset["source_path"]),
                codec="vorbis",
                container="ogg",
                sample_rate=int(source["sample_rate"]),
                channels=int(source["channels"]),
                duration_seconds=float(source["duration_seconds"]),
            )["output"]
            if output != expected_output:
                raise ReleaseError(f"copied Vorbis metadata is stale or tampered: {logical_path}")
        elif mode.reproduce_conversions:
            with tempfile.TemporaryDirectory(prefix="atrinik-sound-playtest-verify-") as temporary:
                reproduced = convert_legacy_asset(source_asset, Path(temporary), toolchain)
                generated = Path(temporary) / str(source_asset["generated_path"])
                reproduced_output = reproduced["output"]
                assert isinstance(reproduced_output, dict)
                expected_output = playtest_output_record(
                    source_asset,
                    generated,
                    codec="opus",
                    container="ogg",
                    sample_rate=int(reproduced_output["sample_rate"]),
                    channels=int(reproduced_output["channels"]),
                    duration_seconds=float(reproduced_output["duration_seconds"]),
                )["output"]
                if output != expected_output:
                    raise ReleaseError(f"converted Opus output is not deterministic: {logical_path}")
        else:
            expected_sample_rate = int(toolchain["quality_budget"]["sample_rate"])  # type: ignore[index]
            expected_output_metadata = {
                "codec": "opus",
                "container": "ogg",
                "sample_rate": expected_sample_rate,
                "channels": int(render["channels"]),
            }
            if {
                key: output.get(key) for key in expected_output_metadata
            } != expected_output_metadata:
                raise ReleaseError(f"converted Opus metadata is stale or tampered: {logical_path}")
            if (
                render["renderer"] != "wildmidi"
                and abs(
                    float(output["duration_seconds"]) - float(source["duration_seconds"])
                ) > float(toolchain["duration_tolerance_seconds"])
            ):
                raise ReleaseError(f"converted Opus duration is stale or tampered: {logical_path}")
        if mode.decode_payloads:
            run_sdl_probe(
                payload,
                expected_frames=round(
                    float(output["duration_seconds"])
                    * int(toolchain["quality_budget"]["sample_rate"])  # type: ignore[index]
                ),
                behaviors=(),
                expected_channels=int(output["channels"]),
                toolchain=toolchain,
                strict_playtest=True,
            )

    logical_paths = sorted(expected_by_path)
    if logical_tree_sha256(root, logical_paths) != manifest_value.get("output_tree_sha256"):
        raise ReleaseError("playtest output-tree digest mismatch")
    if clean_source_coordinates() != (source_commit, source_tree):
        raise ReleaseError("sound checkout changed while verifying the playtest tree")
    if (
        sha256(SOURCE_MANIFEST) != expected_coordinates["source_manifest_sha256"]
        or sha256(PLAYTEST_TOOLCHAIN) != expected_coordinates["toolchain_sha256"]
        or sha256(SCHEMA_ROOT / "playtest-manifest-v1.schema.json")
        != expected_coordinates["schema_sha256"]
        or canonical_json(checked_playtest_toolchain()) != canonical_json(toolchain)
        or verify_toolchain(toolchain, strict_playtest=True) != versions
    ):
        raise ReleaseError("playtest verification inputs changed during verification")
    return manifest_value


def verify_paired_playtest_trees(
    first: Path, second: Path,
) -> tuple[dict[str, object], float, float]:
    """Compare two retained trees before one no-rerender independent decode."""
    with anchored_playtest_output(first, create_parents=False) as (first_root, _first_lexical), \
            anchored_playtest_output(second, create_parents=False) as (second_root, _second_lexical):
        first_identity = first_root.stat(follow_symlinks=False)
        second_identity = second_root.stat(follow_symlinks=False)
        if (first_identity.st_dev, first_identity.st_ino) == (
            second_identity.st_dev, second_identity.st_ino,
        ):
            raise ReleaseError("paired playtest verification requires two distinct trees")
        with playtest_verification_lock(first_root), playtest_verification_lock(second_root), \
                stable_playtest_snapshot(first_root) as first_snapshot, \
                stable_playtest_snapshot(second_root) as second_snapshot:
            comparison_started = time.monotonic()
            first_manifest = verify_playtest_tree(
                first_snapshot.path,
                require_build_path=False,
                mode=PlaytestVerificationMode.BUILT_TREE,
                _trusted_snapshot=True,
            )
            second_manifest = verify_playtest_tree(
                second_snapshot.path,
                require_build_path=False,
                mode=PlaytestVerificationMode.BUILT_TREE,
                _trusted_snapshot=True,
            )
            if canonical_json(first_manifest) != canonical_json(second_manifest):
                raise ReleaseError("independent playtest-tree manifests differ")
            comparison_seconds = time.monotonic() - comparison_started
            decode_started = time.monotonic()
            verified_manifest = verify_playtest_tree(
                first_snapshot.path,
                require_build_path=False,
                mode=PlaytestVerificationMode.PAIRED_TREE,
                _trusted_snapshot=True,
            )
            decode_seconds = time.monotonic() - decode_started
    return verified_manifest, comparison_seconds, decode_seconds


def install_directory_noreplace(staging: Path, destination: Path) -> None:
    """Atomically install a directory without replacing any existing entry."""
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise ReleaseError("atomic no-replace directory installation is unavailable") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(staging),
        -100,
        os.fsencode(destination),
        1,  # RENAME_NOREPLACE
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ReleaseError(f"playtest output appeared concurrently: {destination}")
    if error in {errno.ENOSYS, errno.EINVAL}:
        raise ReleaseError("atomic no-replace directory installation is unavailable")
    raise OSError(error, os.strerror(error), str(destination))


def _build_playtest_tree_anchored(output_directory: Path) -> None:
    with playtest_output_lock(output_directory):
        source_commit, source_tree = clean_source_coordinates()
        source_manifest = checked_manifest()
        blockers = validate_manifest(source_manifest, verify_tracked=True)
        toolchain = checked_playtest_toolchain()
        versions = verify_toolchain(toolchain, strict_playtest=True)
        source_manifest_sha256 = sha256(SOURCE_MANIFEST)
        toolchain_sha256 = sha256(PLAYTEST_TOOLCHAIN)
        schema_sha256 = sha256(SCHEMA_ROOT / "playtest-manifest-v1.schema.json")
        if output_directory.exists():
            verify_playtest_tree(
                output_directory,
                require_build_path=False,
                mode=PlaytestVerificationMode.EXISTING_TREE,
            )
            return
        assets = playtest_assets(source_manifest, toolchain)
        with tempfile.TemporaryDirectory(prefix=f".{output_directory.name}.staging-", dir=output_directory.parent) as temporary:
            staging = Path(temporary)
            generated_assets: list[dict[str, object]] = []
            for asset in assets:
                assert isinstance(asset, dict)
                logical_path = str(asset["logical_path"])
                source = asset["source"]
                assert isinstance(source, dict)
                destination = staging / logical_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source["codec"] == "vorbis":
                    shutil.copyfile(ROOT / str(asset["source_path"]), destination)
                    generated_assets.append(playtest_output_record(
                        asset,
                        destination,
                        codec="vorbis",
                        container="ogg",
                        sample_rate=int(source["sample_rate"]),
                        channels=int(source["channels"]),
                        duration_seconds=float(source["duration_seconds"]),
                    ))
                else:
                    with tempfile.TemporaryDirectory(prefix="atrinik-sound-playtest-convert-") as conversion_directory:
                        converted = convert_playtest_asset(asset, Path(conversion_directory), toolchain)
                        converted_output = converted["output"]
                        assert isinstance(converted_output, dict)
                        generated = Path(conversion_directory) / str(asset["generated_path"])
                        shutil.move(generated, destination)
                        generated_assets.append(playtest_output_record(
                            asset,
                            destination,
                            codec="opus",
                            container="ogg",
                            sample_rate=int(converted_output["sample_rate"]),
                            channels=int(converted_output["channels"]),
                            duration_seconds=float(converted_output["duration_seconds"]),
                        ))
            marker_payload = canonical_json(PLAYTEST_MARKER)
            blockers_payload = canonical_json(blocker_report(source_manifest, blockers))
            (staging / PLAYTEST_MARKER_NAME).write_bytes(marker_payload)
            (staging / PLAYTEST_BLOCKERS_NAME).write_bytes(blockers_payload)
            schema_directory = staging / "schemas"
            schema_directory.mkdir()
            shutil.copyfile(
                SCHEMA_ROOT / "playtest-manifest-v1.schema.json",
                schema_directory / "playtest-manifest-v1.schema.json",
            )
            playtest_manifest = {
                "$schema": "schemas/playtest-manifest-v1.schema.json",
                "schema_version": 1,
                "playtest_only": True,
                "publishable": False,
                "source_commit": source_commit,
                "source_tree": source_tree,
                "source_manifest_sha256": source_manifest_sha256,
                "toolchain_sha256": toolchain_sha256,
                "schema_sha256": schema_sha256,
                "tool_versions": versions,
                "marker_sha256": hashlib.sha256(marker_payload).hexdigest(),
                "blocker_report_sha256": hashlib.sha256(blockers_payload).hexdigest(),
                "blocker_count": len(blockers),
                "logical_path_count": len(generated_assets),
                "copied_vorbis_count": sum(asset["mapping"] == "copy" for asset in generated_assets),
                "converted_opus_count": sum(asset["mapping"] == "render-opus" for asset in generated_assets),
                "output_tree_sha256": logical_tree_sha256(staging, [str(asset["logical_path"]) for asset in generated_assets]),
                "assets": generated_assets,
            }
            validate_playtest_manifest(playtest_manifest)
            (staging / PLAYTEST_MANIFEST_NAME).write_bytes(canonical_json(playtest_manifest))
            root_location = [staging]
            with stable_playtest_snapshot(
                staging, root_location=root_location,
            ) as verified:
                verify_playtest_tree(
                    verified.path,
                    require_build_path=False,
                    mode=PlaytestVerificationMode.BUILT_TREE,
                    _trusted_snapshot=True,
                )
                if clean_source_coordinates() != (source_commit, source_tree):
                    raise ReleaseError("sound checkout changed while building the playtest tree")
                if (
                    sha256(SOURCE_MANIFEST) != source_manifest_sha256
                    or sha256(PLAYTEST_TOOLCHAIN) != toolchain_sha256
                    or sha256(SCHEMA_ROOT / "playtest-manifest-v1.schema.json") != schema_sha256
                    or canonical_json(checked_playtest_toolchain()) != canonical_json(toolchain)
                    or verify_toolchain(toolchain, strict_playtest=True) != versions
                ):
                    raise ReleaseError("playtest generation inputs changed while building")
                verified.reject_mutations()
                if output_directory.exists():
                    raise ReleaseError(f"playtest output appeared concurrently: {output_directory}")
                install_directory_noreplace(staging, output_directory)
                root_location[0] = output_directory


def build_playtest_tree(output_directory: Path) -> Path:
    with anchored_playtest_output(output_directory, create_parents=True) as (anchored, lexical):
        _build_playtest_tree_anchored(anchored)
        return lexical


def classic_runtime_remediation_report(
    source_manifest: dict[str, object], blockers: list[dict[str, object]],
    source_commit: str, source_tree: str,
) -> dict[str, object]:
    categories = sorted({str(finding.get("category")) for finding in blockers})
    report = {
        "$schema": f"schemas/{CLASSIC_REMEDIATION_SCHEMA_NAME}",
        "schema_version": 1,
        "classification": "nonblocking-modernization",
        "release_boundary": (
            "These findings remain required modernization work, but do not block "
            "republication of Atrinik's existing Classic sound corpus."
        ),
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "source_count": source_manifest["audio_source_count"],
        "count": len(blockers),
        "category_counts": {
            category: sum(str(finding.get("category")) == category for finding in blockers)
            for category in categories
        },
        "findings": blockers,
    }
    validate_classic_remediation_report(report)
    return report


def validate_classic_remediation_report(report: dict[str, object]) -> None:
    validate_schema_instance(
        report, checked_schema(CLASSIC_REMEDIATION_SCHEMA_NAME),
    )
    findings = report.get("findings")
    counts = report.get("category_counts")
    if not isinstance(findings, list) or not isinstance(counts, dict):
        raise ReleaseError("Classic remediation report is incomplete")
    actual: dict[str, int] = {}
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("category"), str):
            raise ReleaseError("Classic remediation finding is incomplete")
        category = str(finding["category"])
        actual[category] = actual.get(category, 0) + 1
    if report.get("count") != len(findings) or counts != actual:
        raise ReleaseError("Classic remediation finding counts do not match")


def _classic_runtime_static_sources() -> tuple[str, ...]:
    return (
        "README.md",
        "background/LICENSE",
        "background/README.md",
        "effects/LICENSE",
        "effects/README.md",
        "manifests/license-reviews.json",
        "manifests/classic-audio-toolchain.json",
        "manifests/source-assets.json",
        "manifests/source-replacements.json",
        "manifests/vorbis-quality-reviews.json",
        "schemas/classic-audio-toolchain-v1.schema.json",
        "schemas/classic-remediation-v1.schema.json",
        "schemas/license-reviews-v2.schema.json",
        "schemas/source-assets-v1.schema.json",
        "schemas/source-replacements-v1.schema.json",
        "schemas/vorbis-quality-reviews-v2.schema.json",
    )


def _copy_classic_runtime_contracts(root: Path, toolchain: dict[str, object]) -> set[str]:
    copied: set[str] = set()
    for relative in _classic_runtime_static_sources():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
        copied.add(relative)
    schema_relative = f"schemas/{CLASSIC_RUNTIME_SCHEMA_NAME}"
    schema_destination = root / schema_relative
    schema_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SCHEMA_ROOT / CLASSIC_RUNTIME_SCHEMA_NAME, schema_destination)
    copied.add(schema_relative)
    license_texts = toolchain.get("license_texts")
    if not isinstance(license_texts, dict):
        raise ReleaseError("Classic runtime toolchain license texts must be an object")
    for contract in license_texts.values():
        if not isinstance(contract, dict):
            raise ReleaseError("Classic runtime toolchain license contract is invalid")
        relative = str(contract.get("archive_path", ""))
        source = Path(str(contract.get("installed_path", "")))
        pure = PurePosixPath(relative)
        if (
            not relative.startswith("licenses/") or pure.is_absolute()
            or ".." in pure.parts or pure.as_posix() != relative
        ):
            raise ReleaseError("Classic runtime toolchain license archive path is unsafe")
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied.add(relative)
    return copied


def _require_classic_payload_codec(path: Path, codec: object, logical_path: str) -> None:
    with path.open("rb") as stream:
        header = stream.read(65536)
    expected = b"\x01vorbis" if codec == "vorbis" else b"OpusHead" if codec == "opus" else None
    if not header.startswith(b"OggS") or expected is None or expected not in header:
        raise ReleaseError(f"Classic runtime payload codec mismatch: {logical_path}")
    forbidden = (b"MThd", b"fLaC", b"Extended Module: ", b"SCRM")
    if any(header.startswith(signature) for signature in forbidden):
        raise ReleaseError(f"Classic runtime contains a raw authored codec: {logical_path}")


def verify_classic_runtime_root(
    root: Path, *, release_tag: str, source_commit: str, source_tree: str,
) -> dict[str, object]:
    source_manifest = checked_manifest()
    blockers = validate_manifest(source_manifest, verify_tracked=True)
    toolchain = checked_classic_toolchain()
    versions = verify_toolchain(toolchain, strict_playtest=True)
    expected_assets = legacy_path_assets(source_manifest, toolchain)
    expected_by_path = {str(asset["logical_path"]): asset for asset in expected_assets}

    manifest_path = root / CLASSIC_RUNTIME_MANIFEST_NAME
    manifest_payload = manifest_path.read_bytes() if manifest_path.is_file() else b""
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest_payload != canonical_json(manifest):
        raise ReleaseError("Classic runtime manifest is missing or not canonical JSON")
    validate_classic_runtime_manifest(manifest)
    expected_coordinates = {
        "release_tag": release_tag,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "toolchain_sha256": sha256(CLASSIC_TOOLCHAIN),
        "tool_versions": versions,
        "schema_sha256": sha256(SCHEMA_ROOT / CLASSIC_RUNTIME_SCHEMA_NAME),
    }
    for key, expected in expected_coordinates.items():
        if manifest.get(key) != expected:
            raise ReleaseError(f"Classic runtime manifest has stale or tampered {key}")

    remediation = classic_runtime_remediation_report(
        source_manifest, blockers, source_commit, source_tree,
    )
    remediation_payload = canonical_json(remediation)
    remediation_path = root / CLASSIC_RUNTIME_REMEDIATION_NAME
    if not remediation_path.is_file() or remediation_path.read_bytes() != remediation_payload:
        raise ReleaseError("Classic runtime remediation report is missing, stale, or tampered")
    if manifest.get("remediation_report_sha256") != hashlib.sha256(remediation_payload).hexdigest():
        raise ReleaseError("Classic runtime remediation report hash mismatch")
    if manifest.get("remediation_finding_count") != len(blockers):
        raise ReleaseError("Classic runtime remediation count mismatch")

    packaged_schema = root / "schemas" / CLASSIC_RUNTIME_SCHEMA_NAME
    if not packaged_schema.is_file() or sha256(packaged_schema) != manifest["schema_sha256"]:
        raise ReleaseError("Classic runtime schema is missing or tampered")
    for relative in _classic_runtime_static_sources():
        packaged = root / relative
        if not packaged.is_file() or sha256(packaged) != sha256(ROOT / relative):
            raise ReleaseError(f"Classic runtime contract is missing or tampered: {relative}")
    license_texts = toolchain.get("license_texts")
    assert isinstance(license_texts, dict)
    for contract in license_texts.values():
        assert isinstance(contract, dict)
        packaged = root / str(contract["archive_path"])
        if not packaged.is_file() or sha256(packaged) != contract["sha256"]:
            raise ReleaseError(f"Classic runtime toolchain license is missing or tampered: {packaged}")

    manifest_assets = manifest.get("assets")
    assert isinstance(manifest_assets, list)
    actual_by_path = {
        str(asset["logical_path"]): asset for asset in manifest_assets if isinstance(asset, dict)
    }
    if set(actual_by_path) != set(expected_by_path):
        raise ReleaseError("Classic runtime does not have exact logical-path closure")
    for logical_path, source_asset in expected_by_path.items():
        actual = actual_by_path[logical_path]
        source = source_asset["source"]
        output = actual.get("output")
        assert isinstance(source, dict)
        if not isinstance(output, dict):
            raise ReleaseError(f"Classic runtime output metadata is missing: {logical_path}")
        expected_static = {
            "logical_path": logical_path,
            "source_path": source_asset["source_path"],
            "mapping": "copy" if source["codec"] == "vorbis" else "render-opus",
            "source": {
                "sha256": source["sha256"],
                "codec": source["codec"],
                "container": source["container"],
            },
        }
        if {key: actual.get(key) for key in expected_static} != expected_static:
            raise ReleaseError(f"Classic runtime mapping is stale or tampered: {logical_path}")
        payload = root / logical_path
        if not payload.is_file() or payload.is_symlink():
            raise ReleaseError(f"Classic runtime payload is missing or unsafe: {logical_path}")
        if sha256(payload) != output.get("sha256") or payload.stat().st_size != output.get("size_bytes"):
            raise ReleaseError(f"Classic runtime payload hash or size mismatch: {logical_path}")
        _require_classic_payload_codec(payload, output.get("codec"), logical_path)
        if source["codec"] == "vorbis":
            expected_output = playtest_output_record(
                source_asset, ROOT / str(source_asset["source_path"]),
                codec="vorbis", container="ogg",
                sample_rate=int(source["sample_rate"]),
                channels=int(source["channels"]),
                duration_seconds=float(source["duration_seconds"]),
            )["output"]
            if output != expected_output:
                raise ReleaseError(f"Classic runtime Vorbis copy is not byte-identical: {logical_path}")
        run_sdl_probe(
            payload,
            expected_frames=round(
                float(output["duration_seconds"])
                * int(toolchain["quality_budget"]["sample_rate"])  # type: ignore[index]
            ),
            behaviors=(), expected_channels=int(output["channels"]),
            toolchain=toolchain, strict_playtest=True,
        )
    logical_paths = sorted(expected_by_path)
    if logical_tree_sha256(root, logical_paths) != manifest.get("output_tree_sha256"):
        raise ReleaseError("Classic runtime logical-tree digest mismatch")
    for representative in (
        "background/intro.ogg", "background/fireside.mid",
        "background/tutorialisland.mid", "effects/campfire.ogg",
    ):
        if representative not in actual_by_path:
            raise ReleaseError(f"Classic runtime representative path is missing: {representative}")
    expected_files = set(logical_paths) | set(_classic_runtime_static_sources()) | {
        CLASSIC_RUNTIME_MANIFEST_NAME,
        CLASSIC_RUNTIME_REMEDIATION_NAME,
        f"schemas/{CLASSIC_RUNTIME_SCHEMA_NAME}",
        "SHA256SUMS",
    }
    expected_files.update(
        str(contract["archive_path"])
        for contract in license_texts.values()
        if isinstance(contract, dict)
    )
    actual_files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ReleaseError(f"Classic runtime contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            actual_files.add(path.relative_to(root).as_posix())
    if actual_files != expected_files:
        raise ReleaseError("Classic runtime contains missing or unexpected files")
    verify_tree_checksums(root)
    if clean_source_coordinates() != (source_commit, source_tree):
        raise ReleaseError("sound checkout changed while verifying the Classic runtime")
    return manifest


def build_classic_runtime(tag: str, output_directory: Path) -> tuple[Path, Path]:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ReleaseError(f"invalid release tag: {tag}")
    clean_commit, clean_tree = clean_source_coordinates()
    source_commit = source_revision("ATRINIK_SOURCE_COMMIT", "HEAD")
    source_tree = source_revision("ATRINIK_SOURCE_TREE", "HEAD^{tree}")
    if (source_commit, source_tree) != (clean_commit, clean_tree):
        raise ReleaseError("Classic runtime source coordinates do not match the clean checkout")
    verify_release_tag(tag, source_commit, source_tree)
    epoch_text = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch_text is None or not epoch_text.isdigit():
        raise ReleaseError("SOURCE_DATE_EPOCH must be a non-negative integer")
    epoch = int(epoch_text)
    source_manifest = checked_manifest()
    blockers = validate_manifest(source_manifest, verify_tracked=True)
    toolchain = checked_classic_toolchain()
    versions = verify_toolchain(toolchain, strict_playtest=True)
    assets = legacy_path_assets(source_manifest, toolchain)
    version = tag[1:]
    package = f"atrinik-sound-classic-runtime-{version}"
    output_directory.mkdir(parents=True, exist_ok=True)
    if output_directory.is_symlink() or not output_directory.is_dir():
        raise ReleaseError(f"Classic runtime output is not a regular directory: {output_directory}")
    archive = output_directory / f"{package}.tar.gz"
    remediation_asset = output_directory / f"{package}-REMEDIATION.json"
    if archive.exists() or remediation_asset.exists():
        raise ReleaseError("Classic runtime output already exists")
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-classic-runtime-") as temporary:
        staging = Path(temporary) / package
        staging.mkdir(parents=True)
        generated_assets: list[dict[str, object]] = []
        for asset in assets:
            logical_path = str(asset["logical_path"])
            source = asset["source"]
            assert isinstance(source, dict)
            destination = staging / logical_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source["codec"] == "vorbis":
                shutil.copyfile(ROOT / str(asset["source_path"]), destination)
                generated_assets.append(playtest_output_record(
                    asset, destination, codec="vorbis", container="ogg",
                    sample_rate=int(source["sample_rate"]), channels=int(source["channels"]),
                    duration_seconds=float(source["duration_seconds"]),
                ))
            else:
                with tempfile.TemporaryDirectory(prefix="atrinik-sound-classic-convert-") as conversion:
                    converted = convert_legacy_asset(asset, Path(conversion), toolchain)
                    converted_output = converted["output"]
                    assert isinstance(converted_output, dict)
                    shutil.move(Path(conversion) / str(asset["generated_path"]), destination)
                    generated_assets.append(playtest_output_record(
                        asset, destination, codec="opus", container="ogg",
                        sample_rate=int(converted_output["sample_rate"]),
                        channels=int(converted_output["channels"]),
                        duration_seconds=float(converted_output["duration_seconds"]),
                    ))
        remediation = classic_runtime_remediation_report(
            source_manifest, blockers, source_commit, source_tree,
        )
        remediation_payload = canonical_json(remediation)
        (staging / CLASSIC_RUNTIME_REMEDIATION_NAME).write_bytes(remediation_payload)
        _copy_classic_runtime_contracts(staging, toolchain)
        classic_manifest = {
            "$schema": f"schemas/{CLASSIC_RUNTIME_SCHEMA_NAME}",
            "schema_version": 1,
            "publishable": True,
            "playtest_only": False,
            "release_tag": tag,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "source_manifest_sha256": sha256(SOURCE_MANIFEST),
            "toolchain_sha256": sha256(CLASSIC_TOOLCHAIN),
            "tool_versions": versions,
            "schema_sha256": sha256(SCHEMA_ROOT / CLASSIC_RUNTIME_SCHEMA_NAME),
            "remediation_report_sha256": hashlib.sha256(remediation_payload).hexdigest(),
            "remediation_finding_count": len(blockers),
            "logical_path_count": len(generated_assets),
            "copied_vorbis_count": sum(asset["mapping"] == "copy" for asset in generated_assets),
            "converted_opus_count": sum(asset["mapping"] == "render-opus" for asset in generated_assets),
            "output_tree_sha256": logical_tree_sha256(
                staging, [str(asset["logical_path"]) for asset in generated_assets],
            ),
            "assets": generated_assets,
        }
        validate_classic_runtime_manifest(classic_manifest)
        (staging / CLASSIC_RUNTIME_MANIFEST_NAME).write_bytes(canonical_json(classic_manifest))
        write_tree_checksums(staging)
        verify_classic_runtime_root(
            staging, release_tag=tag, source_commit=source_commit,
            source_tree=source_tree,
        )
        if clean_source_coordinates() != (source_commit, source_tree):
            raise ReleaseError("sound checkout changed while building the Classic runtime")
        deterministic_archive(staging, archive, package, epoch)
        atomic_write(remediation_asset, remediation_payload)
    return archive, remediation_asset


def verify_classic_runtime_archive(archive: Path, tag: str) -> dict[str, object]:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ReleaseError(f"invalid release tag: {tag}")
    if not archive.is_file() or archive.is_symlink():
        raise ReleaseError(f"Classic runtime archive is missing or unsafe: {archive}")
    version = tag[1:]
    prefix = f"atrinik-sound-classic-runtime-{version}"
    epoch_text = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch_text is None or not epoch_text.isdigit():
        raise ReleaseError("SOURCE_DATE_EPOCH must be a non-negative integer")
    epoch = int(epoch_text)
    source_commit = source_revision("ATRINIK_SOURCE_COMMIT", "HEAD")
    source_tree = source_revision("ATRINIK_SOURCE_TREE", "HEAD^{tree}")
    if clean_source_coordinates() != (source_commit, source_tree):
        raise ReleaseError("Classic runtime verification source is not the exact clean checkout")
    verify_release_tag(tag, source_commit, source_tree)
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-classic-verify-") as temporary:
        extracted = Path(temporary) / prefix
        extracted.mkdir()
        seen: set[str] = set()
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            names = [member.name for member in members]
            if names != sorted(names) or not members or len(members) > CLASSIC_RUNTIME_MAX_FILES:
                raise ReleaseError("Classic runtime archive order is not canonical")
            total_size = 0
            for member in members:
                expected_prefix = f"{prefix}/"
                if not member.isfile() or not member.name.startswith(expected_prefix):
                    raise ReleaseError(f"Classic runtime archive member is unsafe: {member.name}")
                relative = PurePosixPath(member.name[len(expected_prefix):])
                if (
                    not relative.parts or relative.is_absolute() or ".." in relative.parts
                    or relative.as_posix() in seen or len(member.name.encode("utf-8")) > 255
                ):
                    raise ReleaseError(f"Classic runtime archive path is unsafe: {member.name}")
                total_size += member.size
                if (
                    member.size <= 0 or member.size > CLASSIC_RUNTIME_MAX_FILE_BYTES
                    or total_size > CLASSIC_RUNTIME_MAX_TOTAL_BYTES
                ):
                    raise ReleaseError(f"Classic runtime archive member is oversized: {member.name}")
                if (
                    member.mtime != epoch or member.mode != 0o644
                    or member.uid != 0 or member.gid != 0
                    or member.uname != "root" or member.gname != "root"
                ):
                    raise ReleaseError(f"Classic runtime archive metadata is not deterministic: {member.name}")
                seen.add(relative.as_posix())
                source = bundle.extractfile(member)
                if source is None:
                    raise ReleaseError(f"Classic runtime archive member cannot be read: {member.name}")
                destination = extracted.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
        return verify_classic_runtime_root(
            extracted, release_tag=tag,
            source_commit=source_commit, source_tree=source_tree,
        )


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


def eligible_quality_review_assets(
    manifest: dict[str, object],
    asset_class: str | None = None,
) -> list[dict[str, object]]:
    assets = manifest["assets"]
    assert isinstance(assets, list)
    return sorted([
        asset for asset in assets
        if isinstance(asset, dict)
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
    selected = eligible_quality_review_assets(manifest, asset_class)
    if not selected:
        raise ReleaseError("no license-approved sources await quality review")
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
        source_relative = PurePosixPath("sources") / PurePosixPath(str(asset["source_path"]))
        source_output = output_directory / source_relative
        source_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / str(asset["source_path"]), source_output)
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
        for asset in eligible_quality_review_assets(current_manifest, asset_class)
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
        expected_source_path = (PurePosixPath("sources") / PurePosixPath(str(current_asset["source_path"]))).as_posix()
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
    print(canonical_json(blocker_report(manifest, blockers)).decode("utf-8"), end="")


def command_classic_release_notes(_arguments: argparse.Namespace) -> None:
    manifest = checked_manifest()
    blockers = validate_manifest(manifest, verify_tracked=True)
    print(classic_release_notes(blockers), end="")


def command_build(arguments: argparse.Namespace) -> None:
    output = build_runtime(arguments.tag, Path(arguments.output_directory), fixtures=arguments.fixtures)
    print(output)


def command_build_playtest_tree(arguments: argparse.Namespace) -> None:
    output = build_playtest_tree(Path(arguments.output_directory))
    manifest = read_json(output / PLAYTEST_MANIFEST_NAME)
    assert isinstance(manifest, dict)
    print(
        f"built {manifest['logical_path_count']} playtest paths; "
        f"tree SHA-256: {manifest['output_tree_sha256']}"
    )


def command_build_classic_runtime(arguments: argparse.Namespace) -> None:
    archive, remediation = build_classic_runtime(
        arguments.tag, Path(arguments.output_directory),
    )
    print(archive)
    print(remediation)


def command_verify_classic_runtime(arguments: argparse.Namespace) -> None:
    manifest = verify_classic_runtime_archive(
        Path(arguments.archive), arguments.tag,
    )
    print(
        f"verified {manifest['logical_path_count']} Classic runtime paths; "
        f"tree SHA-256: {manifest['output_tree_sha256']}"
    )


def command_verify_playtest_tree(arguments: argparse.Namespace) -> None:
    output = Path(arguments.output_directory)
    with anchored_playtest_output(output, create_parents=False) as (anchored, _lexical):
        with playtest_verification_lock(anchored):
            manifest = verify_playtest_tree(anchored, require_build_path=False)
    print(
        f"verified {manifest['logical_path_count']} playtest paths; "
        f"tree SHA-256: {manifest['output_tree_sha256']}"
    )


def command_verify_paired_playtest_trees(arguments: argparse.Namespace) -> None:
    manifest, comparison_seconds, decode_seconds = verify_paired_playtest_trees(
        Path(arguments.first_output_directory),
        Path(arguments.second_output_directory),
    )
    print(f"playtest phase timing: compare={comparison_seconds:.3f}s")
    print(f"playtest phase timing: independent-decode={decode_seconds:.3f}s")
    print(
        f"verified paired {manifest['logical_path_count']} playtest paths; "
        f"tree SHA-256: {manifest['output_tree_sha256']}"
    )


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
    release_notes = commands.add_parser(
        "classic-release-notes",
        help="print the Classic restoration modernization release-note fragment",
    )
    release_notes.set_defaults(function=command_classic_release_notes)
    build = commands.add_parser("build-runtime", help="build the full or fixture Opus archive")
    build.add_argument("tag")
    build.add_argument("output_directory")
    build.add_argument("--fixtures", action="store_true", help="build the six-asset CI fixture archive")
    build.set_defaults(function=command_build)
    classic_runtime = commands.add_parser(
        "build-classic-runtime",
        help="build the publishable Classic restoration runtime archive",
    )
    classic_runtime.add_argument("tag")
    classic_runtime.add_argument("output_directory")
    classic_runtime.set_defaults(function=command_build_classic_runtime)
    verify_classic_runtime = commands.add_parser(
        "verify-classic-runtime",
        help="independently verify and fully decode a Classic restoration runtime archive",
    )
    verify_classic_runtime.add_argument("tag")
    verify_classic_runtime.add_argument("archive")
    verify_classic_runtime.set_defaults(function=command_verify_classic_runtime)
    playtest = commands.add_parser(
        "build-playtest-tree",
        help="build the complete local-only Classic compatibility tree",
    )
    playtest.add_argument("output_directory")
    playtest.set_defaults(function=command_build_playtest_tree)
    verify_playtest = commands.add_parser(
        "verify-playtest-tree",
        help="verify and fully decode a local-only Classic compatibility tree",
    )
    verify_playtest.add_argument("output_directory")
    verify_playtest.set_defaults(function=command_verify_playtest_tree)
    verify_playtest_pair = commands.add_parser(
        "verify-paired-playtest-trees",
        help="compare two complete trees and independently decode one byte-identical result",
    )
    verify_playtest_pair.add_argument("first_output_directory")
    verify_playtest_pair.add_argument("second_output_directory")
    verify_playtest_pair.set_defaults(function=command_verify_paired_playtest_trees)
    candidate = commands.add_parser("build-review-candidate", help="build one license-approved non-publishing quality-review candidate")
    candidate.add_argument("logical_path")
    candidate.add_argument("output_directory")
    candidate.set_defaults(function=command_build_review_candidate)
    bundle = commands.add_parser("build-review-bundle", help="build all eligible non-publishing quality-review candidates and a listening worksheet")
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
