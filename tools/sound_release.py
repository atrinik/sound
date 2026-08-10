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


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "manifests" / "source-assets.json"
TOOLCHAIN = ROOT / "manifests" / "audio-toolchain.json"
FIXTURE_PLAN = ROOT / "manifests" / "fixture-plan.json"
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


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read JSON contract {path}: {exc}") from exc


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def discover_sources() -> list[Path]:
    sources: list[Path] = []
    for directory in (ROOT / "background", ROOT / "effects"):
        for path in directory.iterdir():
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in AUDIO_SUFFIXES:
                sources.append(path)
    return sorted(sources, key=lambda path: path.relative_to(ROOT).as_posix())


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


def tracker_metadata(path: Path) -> SourceMetadata:
    duration_path = ROOT / "background" / "durations" / path.name
    try:
        duration = float(duration_path.read_text(encoding="ascii").strip())
    except (OSError, ValueError) as exc:
        if SOURCE_MANIFEST.is_file():
            existing = read_json(SOURCE_MANIFEST)
            if isinstance(existing, dict) and isinstance(existing.get("assets"), list):
                relative = path.relative_to(ROOT).as_posix()
                for asset in existing["assets"]:
                    if not isinstance(asset, dict) or asset.get("source_path") != relative:
                        continue
                    source = asset.get("source")
                    if (
                        isinstance(source, dict)
                        and source.get("sha256") == sha256(path)
                        and isinstance(source.get("duration_seconds"), (int, float))
                    ):
                        duration = float(source["duration_seconds"])
                        break
                else:
                    raise ReleaseError(
                        f"tracker metadata changed for {relative}; refresh it with the pinned openmpt123 tool"
                    ) from exc
            else:
                raise ReleaseError(f"missing tracker metadata for {relative}") from exc
        else:
            raise ReleaseError(f"missing tracker metadata for {path.relative_to(ROOT)}") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ReleaseError(f"non-positive tracker duration for {path.relative_to(ROOT)}")
    return SourceMetadata(duration, None, None)


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


def notice_status(notice: dict[str, str] | None) -> tuple[str, str | None]:
    if notice is None:
        return "blocked", "missing exact asset notice"
    description = notice["description"].lower()
    blocked = (
        "permission to use",
        "freeware",
        "non-commercial",
        "noncommercial",
        "cc-by-nc",
        "cc by-nc",
        "touhou",
    )
    if any(term in description for term in blocked):
        return "blocked", "ambiguous or noncommercial transformation terms"
    if re.search(r"(?:^|\s)gpl(?:\s|:|$)", description) and not re.search(
        r"gpl(?:v|\s*)[23](?:\.0)?", description
    ):
        return "blocked", "GPL version or exact terms are incomplete"
    if re.search(r"cc-?by(?:\s|:|$)", description) and not re.search(r"cc-?by(?:-sa)?\s+[0-9]", description):
        return "blocked", "Creative Commons version is incomplete"
    return "allowed", None


def codec_contract(suffix: str) -> tuple[str, str, str]:
    if suffix == ".mid":
        return "midi", "standard-midi-file", "timidity"
    if suffix in TRACKER_SUFFIXES:
        return suffix[1:], "tracker-module", "openmpt123"
    if suffix == ".ogg":
        return "vorbis", "ogg", "ffmpeg"
    raise ReleaseError(f"unsupported suffix: {suffix}")


def build_source_manifest() -> dict[str, object]:
    catalogs = {
        "background": notice_catalog(ROOT / "background"),
        "effects": notice_catalog(ROOT / "effects"),
    }
    assets: list[dict[str, object]] = []
    for path in discover_sources():
        relative = path.relative_to(ROOT).as_posix()
        logical = PurePosixPath(relative)
        metadata = source_metadata(path)
        codec, container, renderer = codec_contract(path.suffix.lower())
        notice = catalogs[logical.parts[0]].get(logical.name)
        status, finding = notice_status(notice)
        generated = f"audio/{logical.parent}/{logical.name}.opus"
        channels = metadata.channels if metadata.channels is not None else 2
        bitrate = 80 if channels == 1 else 160
        render_recipes = {
            "timidity": ["timidity", "-c", "{instrument_config}", "-Ow", "-s", "48000", "-o", "{output}", "{input}"],
            "openmpt123": ["openmpt123", "--quiet", "--batch", "--samplerate", "48000", "--channels", "2", "--no-float", "--dither", "0", "--force", "--output", "{output}", "--", "{input}"],
            "ffmpeg": ["ffmpeg", "-nostdin", "-v", "error", "-i", "{input}", "-map_metadata", "-1", "-ar", "48000", "-c:a", "pcm_s16le", "-y", "{output}"],
        }
        asset: dict[str, object] = {
            "id": f"sound:{relative}",
            "logical_path": relative,
            "source_path": relative,
            "generated_path": generated,
            "source": {
                "sha256": sha256(path),
                "codec": codec,
                "container": container,
                "sample_rate": metadata.sample_rate,
                "channels": metadata.channels,
                "duration_seconds": metadata.duration_seconds,
            },
            "render": {
                "renderer": renderer,
                "recipe": render_recipes[renderer],
                "sample_rate": 48_000,
                "channels": channels,
                "tail_policy": "preserve-decoder-eof",
                "loop": logical.parts[0] == "background",
            },
            "encode": {
                "codec": "opus",
                "container": "ogg",
                "bitrate_kbps": bitrate,
                "mode": "vbr",
                "signal": "music" if logical.parts[0] == "background" else "auto",
                "complexity": 10,
                "serial": int(sha256(path)[0:8], 16),
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
                "notice_reference": notice["reference"] if notice else None,
                "blocking_finding": finding,
            },
        }
        assets.append(asset)
    return {
        "schema_version": 1,
        "source_revision": "generated-from-git-tree",
        "audio_source_count": len(assets),
        "source_size_bytes": sum((ROOT / str(asset["source_path"])).stat().st_size for asset in assets),
        "assets": assets,
    }


def validate_manifest(manifest: dict[str, object], *, compare_generated: bool = True) -> list[dict[str, object]]:
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ReleaseError("source manifest assets must be an array")
    discovered = discover_sources()
    if len(assets) != len(discovered):
        raise ReleaseError(f"source manifest has {len(assets)} assets; discovered {len(discovered)}")
    logical: set[str] = set()
    generated: set[str] = set()
    blockers: list[dict[str, object]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise ReleaseError("source manifest asset must be an object")
        logical_path = asset.get("logical_path")
        generated_path = asset.get("generated_path")
        if not isinstance(logical_path, str) or logical_path in logical:
            raise ReleaseError(f"duplicate or invalid logical path: {logical_path!r}")
        if not isinstance(generated_path, str) or generated_path in generated:
            raise ReleaseError(f"duplicate or invalid generated path: {generated_path!r}")
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
    value = read_json(TOOLCHAIN)
    if not isinstance(value, dict):
        raise ReleaseError("toolchain root must be an object")
    required = {"ffmpeg", "timidity", "openmpt123", "opusenc", "opusinfo", "sdl3_mixer_probe"}
    tools = value.get("tools")
    if not isinstance(tools, dict) or set(tools) != required:
        raise ReleaseError(f"toolchain must define exactly: {', '.join(sorted(required))}")
    bank = value.get("instrument_bank")
    if not isinstance(bank, dict) or not bank.get("recording_distribution_permission"):
        raise ReleaseError("instrument bank must record permission to distribute rendered recordings")
    probe = tools["sdl3_mixer_probe"]
    assert isinstance(probe, dict)
    probe_source = probe.get("source_path")
    probe_sha256 = probe.get("source_sha256")
    if not isinstance(probe_source, str) or not isinstance(probe_sha256, str):
        raise ReleaseError("SDL3_mixer probe must pin its source path and SHA-256")
    probe_path = ROOT / probe_source
    if not probe_path.is_file() or sha256(probe_path) != probe_sha256:
        raise ReleaseError("SDL3_mixer probe source does not match its pinned SHA-256")
    return value


def checked_fixture_plan(manifest: dict[str, object]) -> dict[str, object]:
    value = read_json(FIXTURE_PLAN)
    if not isinstance(value, dict) or not isinstance(value.get("fixtures"), list):
        raise ReleaseError("fixture plan must contain a fixtures array")
    fixtures = value["fixtures"]
    planned = {fixture.get("logical_path") for fixture in fixtures if isinstance(fixture, dict)}
    if planned != set(FIXTURE_PATHS) or len(fixtures) != len(FIXTURE_PATHS):
        raise ReleaseError("fixture plan must cover each pinned fixture exactly once")
    assets = manifest.get("assets")
    assert isinstance(assets, list)
    known = {asset["logical_path"]: asset for asset in assets if isinstance(asset, dict)}
    represented: set[str] = set()
    for fixture in fixtures:
        assert isinstance(fixture, dict)
        logical = fixture["logical_path"]
        if logical not in known:
            raise ReleaseError(f"fixture plan references a missing source: {logical}")
        behaviors = fixture.get("behaviors")
        if not isinstance(behaviors, list) or not all(isinstance(item, str) for item in behaviors):
            raise ReleaseError(f"fixture behaviors must be strings: {logical}")
        represented.update(behaviors)
    required = {"loop", "seek", "stop", "mono", "stereo", "short-effect"}
    if not required <= represented:
        raise ReleaseError(f"fixture plan is missing behaviors: {', '.join(sorted(required - represented))}")
    return value


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


def source_revision(name: str, git_expression: str) -> str:
    value = os.environ.get(name)
    if value is None:
        value = run(["git", "rev-parse", git_expression], capture=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ReleaseError(f"{name} must be a full lowercase Git object ID")
    return value


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
    if renderer == "timidity":
        bank = toolchain["instrument_bank"]
        assert isinstance(bank, dict)
        config_path = Path(os.environ.get("ATRINIK_INSTRUMENT_CONFIG", str(bank["installed_config"])))
        if not config_path.is_file():
            raise ReleaseError(f"pinned instrument-bank config is missing: {config_path}")
        run(["timidity", "-c", str(config_path), "-Ow", "-s", "48000", "-o", str(output), str(source)])
    elif renderer == "openmpt123":
        run(
            [
                "openmpt123",
                "--quiet",
                "--batch",
                "--samplerate",
                "48000",
                "--channels",
                "2",
                "--no-float",
                "--dither",
                "0",
                "--force",
                "--output",
                str(output),
                "--",
                str(source),
            ]
        )
    elif renderer == "ffmpeg":
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-map_metadata", "-1", "-ar", "48000", "-c:a", "pcm_s16le", "-y", str(output)])
    else:
        raise ReleaseError(f"unknown renderer {renderer!r} for {asset['logical_path']}")


def encode_opus(asset: dict[str, object], wave_path: Path, opus_path: Path) -> None:
    encode = asset["encode"]
    assert isinstance(encode, dict)
    serial = int(str(asset["source"]["sha256"])[0:8], 16)  # type: ignore[index]
    command = [
        "opusenc",
        "--quiet",
        "--bitrate", str(encode["bitrate_kbps"]),
        "--vbr",
        "--comp", str(encode["complexity"]),
        "--serial", str(serial),
        "--discard-comments",
    ]
    if encode["signal"] == "music":
        command.append("--music")
    command.extend([str(wave_path), str(opus_path)])
    run(command)


def convert_asset(asset: dict[str, object], output_root: Path, toolchain: dict[str, object]) -> dict[str, object]:
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
        run([str(part).replace("{input}", str(generated)) for part in probe_command])
    source_duration = float(asset["source"]["duration_seconds"])  # type: ignore[index]
    tolerance = float(toolchain["duration_tolerance_seconds"])
    if abs(float(decoded["duration_seconds"]) - source_duration) > tolerance:
        raise ReleaseError(
            f"duration outside {tolerance}s tolerance for {asset['logical_path']}: "
            f"source={source_duration}, decoded={decoded['duration_seconds']}"
        )
    result = dict(asset)
    result["output"] = {
        "sha256": sha256(generated),
        "size_bytes": generated.stat().st_size,
        "codec": "opus",
        "container": "ogg",
        **decoded,
        "rendered_pcm": rendered,
    }
    return result


def deterministic_archive(root: Path, output: Path, prefix: str, epoch: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
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


def build_runtime(tag: str, output_directory: Path, *, fixtures: bool) -> Path:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ReleaseError(f"invalid release tag: {tag}")
    manifest = checked_manifest()
    blockers = validate_manifest(manifest)
    assets = manifest["assets"]
    assert isinstance(assets, list)
    if fixtures:
        checked_fixture_plan(manifest)
        selected = [asset for asset in assets if asset["logical_path"] in FIXTURE_PATHS]
        missing = set(FIXTURE_PATHS) - {str(asset["logical_path"]) for asset in selected}
        if missing:
            raise ReleaseError(f"fixture sources are missing: {', '.join(sorted(missing))}")
    else:
        if blockers:
            raise ReleaseError(
                f"runtime release blocked by {len(blockers)} license/provenance findings; "
                "see manifests/source-assets.json"
            )
        selected = assets
    toolchain = checked_toolchain()
    versions = verify_toolchain(toolchain)
    epoch_text = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch_text is None or not epoch_text.isdigit():
        raise ReleaseError("SOURCE_DATE_EPOCH must be a non-negative integer")
    epoch = int(epoch_text)
    version = tag[1:]
    suffix = "fixture" if fixtures else "runtime"
    package = f"atrinik-sound-{suffix}-{version}"
    with tempfile.TemporaryDirectory(prefix="atrinik-sound-runtime-") as temporary:
        staging = Path(temporary) / package
        staging.mkdir(parents=True)
        converted = [convert_asset(asset, staging, toolchain) for asset in selected]
        runtime_manifest = {
            "schema_version": 1,
            "release_tag": tag,
            "source_commit": source_revision("ATRINIK_SOURCE_COMMIT", "HEAD"),
            "source_tree": source_revision("ATRINIK_SOURCE_TREE", "HEAD^{tree}"),
            "fixture_only": fixtures,
            "source_size_bytes": sum((ROOT / str(asset["source_path"])).stat().st_size for asset in selected),
            "runtime_size_bytes": sum((staging / str(asset["generated_path"])).stat().st_size for asset in converted),
            "quality_budget": toolchain["quality_budget"],
            "tool_versions": versions,
            "toolchain_sha256": sha256(TOOLCHAIN),
            "assets": converted,
        }
        (staging / "manifest.json").write_bytes(canonical_json(runtime_manifest))
        license_root = staging / "licenses"
        license_root.mkdir()
        shutil.copyfile(ROOT / "background" / "LICENSE", license_root / "background-LICENSE")
        shutil.copyfile(ROOT / "effects" / "LICENSE", license_root / "effects-LICENSE")
        shutil.copyfile(TOOLCHAIN, license_root / "audio-toolchain.json")
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
    (output_directory / "SHA256SUMS").write_text(payload, encoding="ascii")


def command_refresh(_arguments: argparse.Namespace) -> None:
    manifest = build_source_manifest()
    SOURCE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_MANIFEST.write_bytes(canonical_json(manifest))
    print(f"wrote {SOURCE_MANIFEST.relative_to(ROOT)} with {manifest['audio_source_count']} assets")


def command_validate(_arguments: argparse.Namespace) -> None:
    manifest = checked_manifest()
    blockers = validate_manifest(manifest)
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
    validate = commands.add_parser("validate", help="validate source, notice, and toolchain contracts")
    validate.set_defaults(function=command_validate)
    blockers = commands.add_parser("blockers", help="print fail-closed runtime findings as JSON")
    blockers.set_defaults(function=command_blockers)
    build = commands.add_parser("build-runtime", help="build the full or fixture Opus archive")
    build.add_argument("tag")
    build.add_argument("output_directory")
    build.add_argument("--fixtures", action="store_true", help="build the six-format CI fixture archive")
    build.set_defaults(function=command_build)
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
