from __future__ import annotations

import hashlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import wave


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sound_release", ROOT / "tools" / "sound_release.py")
assert SPEC is not None and SPEC.loader is not None
sound_release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sound_release
SPEC.loader.exec_module(sound_release)


class SourceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = sound_release.checked_manifest()
        cls.assets = {
            asset["logical_path"]: asset
            for asset in cls.manifest["assets"]
        }

    def test_manifest_is_current_and_closed_over_corpus(self) -> None:
        blockers = sound_release.validate_manifest(self.manifest)
        self.assertEqual(339, self.manifest["audio_source_count"])
        self.assertEqual(339, len(self.assets))
        self.assertEqual(505, len(blockers))
        self.assertEqual(
            {"license/provenance": 309, "quality-review": 196},
            {
                category: sum(finding["category"] == category for finding in blockers)
                for category in {finding["category"] for finding in blockers}
            },
        )

    def test_documented_gate_counts_match_manifest(self) -> None:
        blockers = sound_release.validate_manifest(self.manifest)
        license_count = sum(item["category"] == "license/provenance" for item in blockers)
        documentation = (ROOT / "docs" / "runtime-release.md").read_text(encoding="utf-8")
        documented_license = re.search(r"inventory records ([0-9]+) fail-closed license/provenance", documentation)
        documented_total = re.search(r"producing ([0-9]+) total gates", documentation)
        self.assertIsNotNone(documented_license)
        self.assertIsNotNone(documented_total)
        self.assertEqual(license_count, int(documented_license.group(1)))
        self.assertEqual(len(blockers), int(documented_total.group(1)))
        self.assertEqual(
            {path.relative_to(ROOT).as_posix() for path in sound_release.discover_sources()},
            set(self.assets),
        )

    def test_formats_and_fixture_coverage_match_release_contract(self) -> None:
        counts: dict[str, int] = {}
        for asset in self.assets.values():
            codec = asset["source"]["codec"]
            counts[codec] = counts.get(codec, 0) + 1
        self.assertEqual(
            {"midi": 126, "mod": 5, "s3m": 5, "xm": 7, "vorbis": 196},
            counts,
        )
        fixture_codecs = {
            self.assets[path]["source"]["codec"]
            for path in sound_release.FIXTURE_PATHS
        }
        self.assertEqual({"midi", "mod", "s3m", "xm", "vorbis"}, fixture_codecs)
        self.assertTrue(any(path.startswith("effects/") for path in sound_release.FIXTURE_PATHS))
        plan = sound_release.checked_fixture_plan(self.manifest)
        represented = {
            behavior
            for fixture in plan["fixtures"]
            for behavior in fixture["behaviors"]
        }
        self.assertTrue({"loop", "seek", "stop", "mono", "stereo", "short-effect"} <= represented)

    def test_logical_and_generated_paths_are_unique_and_portable(self) -> None:
        generated = [asset["generated_path"] for asset in self.assets.values()]
        self.assertEqual(len(generated), len(set(generated)))
        for logical, asset in self.assets.items():
            self.assertEqual(logical, logical.lower())
            self.assertNotIn("\\", logical)
            self.assertEqual(f"audio/{logical}.opus", asset["generated_path"])
        self.assertEqual(
            "audio/background/fireside.mid.opus",
            self.assets["background/fireside.mid"]["generated_path"],
        )

    def test_source_hashes_and_sizes_are_exact(self) -> None:
        size = 0
        for logical, asset in self.assets.items():
            path = ROOT / logical
            size += path.stat().st_size
            self.assertEqual(sound_release.sha256(path), asset["source"]["sha256"])
        self.assertEqual(size, self.manifest["source_size_bytes"])

    def test_recursive_discovery_closes_over_nested_audio_candidates(self) -> None:
        directory = ROOT / "effects" / "_nested-discovery-test"
        path = directory / "probe.ogg"
        directory.mkdir()
        try:
            path.write_bytes(b"not parsed by discovery")
            self.assertIn(path, sound_release.discover_sources())
            with self.assertRaisesRegex(sound_release.ReleaseError, "not Git-tracked"):
                sound_release.ensure_sources_tracked(sound_release.discover_sources())
        finally:
            path.unlink(missing_ok=True)
            directory.rmdir()

    def test_duration_drift_is_reconciled(self) -> None:
        restful = self.assets["background/restful_town.mid"]["source"]
        self.assertGreater(restful["duration_seconds"], 0)
        self.assertNotIn("background/fboss.mid", self.assets)
        self.assertNotIn("background/fuego.ogg", self.assets)
        self.assertNotIn("background/toroia.s3m", self.assets)
        self.assertFalse((ROOT / "background" / "durations").exists())

    def test_license_findings_fail_closed(self) -> None:
        self.assertEqual("blocked", self.assets["background/banrril.mid"]["license"]["status"])
        self.assertIn("per-asset license review", self.assets["background/banrril.mid"]["license"]["blocking_finding"])
        for logical in (
            "background/campfire_tales.mid",
            "background/thonkdonk.ogg",
            "effects/arrow_hit.ogg",
        ):
            contract = self.assets[logical]["license"]
            self.assertEqual("blocked", contract["status"])
            self.assertTrue(contract["blocking_finding"])
        unknown = {"description": "Proprietary; no derivatives", "reference": "test:1"}
        self.assertEqual("blocked", sound_release.notice_status(unknown)[0])
        sampling = {
            "description": "example - CC Sampling Plus 1.0",
            "reference": "test:1",
        }
        self.assertEqual("blocked", sound_release.notice_status(sampling)[0])

    def test_candidate_notices_require_evidence_and_reviewed_notices_resolve(self) -> None:
        toolchain = sound_release.checked_toolchain()
        candidates = 0
        allowed = 0
        for logical, asset in self.assets.items():
            contract = asset["license"]
            if not contract["spdx_expression"]:
                continue
            if contract["status"] == "allowed":
                allowed += 1
            else:
                candidates += 1
                self.assertEqual("blocked", contract["status"])
            notice_path, line_text = contract["notice_reference"].rsplit(":", 1)
            line = (ROOT / notice_path).read_text(encoding="utf-8").splitlines()[int(line_text) - 1]
            self.assertIn(Path(logical).name, line)
            self.assertEqual(
                contract["license_text_path"],
                toolchain["license_texts"][contract["spdx_expression"]]["archive_path"],
            )
        self.assertEqual(116, candidates)
        self.assertEqual(30, allowed)

    def test_meritous_project_notice_does_not_approve_music(self) -> None:
        notice = {
            "description": "Meritous - http://www.asceai.net/meritous/ - GPLv3",
            "reference": "background/LICENSE:64",
        }
        status, finding, expression, license_path = sound_release.notice_status(notice)
        self.assertEqual("blocked", status)
        self.assertEqual(
            "notice has no reviewed full-work conversion and redistribution grant",
            finding,
        )
        self.assertIsNone(expression)
        self.assertIsNone(license_path)

    def test_piano_runtime_notices_preserve_supplied_attribution(self) -> None:
        reviews = json.loads((ROOT / "manifests" / "license-reviews.json").read_text())["reviews"]
        reviewed_paths = {
            entry["logical_path"]
            for entry in reviews
            if entry["evidence"]["locator"] == "evidence/piano-midi-de-backgrounds.md"
        }
        self.assertEqual(21, len(reviewed_paths))
        catalog = sound_release.notice_catalog(ROOT / "background")
        for logical_path in reviewed_paths:
            filename = Path(logical_path).name
            notice = catalog[filename]
            with self.subTest(logical_path=logical_path):
                self.assertIn("supplied title:", notice["text"])
                self.assertIn("Copyright", notice["text"])
                self.assertIn("source: https://www.piano-midi.de/", notice["text"])
                self.assertIn("Atrinik modification: MIDI rendered to Opus", notice["text"])
                self.assertEqual(
                    hashlib.sha256(notice["text"].encode()).hexdigest(),
                    self.assets[logical_path]["license"]["notice_sha256"],
                )

    def test_vorbis_quality_review_is_an_immutable_release_gate(self) -> None:
        vorbis = [asset for asset in self.assets.values() if asset["source"]["codec"] == "vorbis"]
        self.assertEqual(196, len(vorbis))
        self.assertTrue(all(asset["quality_review"]["status"] == "blocked" for asset in vorbis))
        self.assertTrue(all(asset["quality_review"]["source_sha256"] == asset["source"]["sha256"] for asset in vorbis))

    def test_quality_review_rejects_malformed_or_mutable_evidence(self) -> None:
        entry = {
            "logical_path": "effects/example.ogg", "status": "passed", "source_sha256": "a" * 64,
            "toolchain_sha256": sound_release.sha256(sound_release.TOOLCHAIN), "output_sha256": "b" * 64,
            "reviewed_by": "reviewer", "reviewed_at": "2026-08-10T00:00:00Z",
            "evidence": {"method": "critical-listening", "artifact_locator": "evidence/README.md", "artifact_sha256": "7fabbf69efe3dba33656e9a9852c70edee2072e9a4ea772a4c1ca91a613b121a", "notes": "schema verification fixture only"},
        }
        document = {"$schema": "../schemas/vorbis-quality-reviews-v1.schema.json", "schema_version": 1, "reviews": [entry]}
        original_read_json = sound_release.read_json
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: document if path == sound_release.QUALITY_REVIEWS else original_read_json(path)):
            self.assertIn("effects/example.ogg", sound_release.checked_quality_reviews())
        broken = copy.deepcopy(document)
        broken["reviews"][0]["reviewed_at"] = "yesterday"
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: broken if path == sound_release.QUALITY_REVIEWS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "timestamp"):
                sound_release.checked_quality_reviews()
        wrong_hash = copy.deepcopy(document)
        wrong_hash["reviews"][0]["evidence"]["artifact_sha256"] = "0" * 64
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: wrong_hash if path == sound_release.QUALITY_REVIEWS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "hash mismatch"):
                sound_release.checked_quality_reviews()

    def test_review_and_encoding_contracts_detect_immutable_input_drift(self) -> None:
        reviewed = json.loads((ROOT / "manifests" / "license-reviews.json").read_text())
        self.assertEqual(30, len(reviewed["reviews"]))
        drifted = copy.deepcopy(self.manifest)
        drifted["assets"][0]["encode"]["bitrate_kbps"] += 1
        with self.assertRaisesRegex(sound_release.ReleaseError, "stale"):
            sound_release.validate_manifest(drifted)

        original_read_json = sound_release.read_json
        for field, replacement in (
            ("reviewed_by", "different-reviewer"),
            ("reviewed_at", "2026-08-10T06:20:37Z"),
        ):
            altered = copy.deepcopy(reviewed)
            altered["reviews"][0][field] = replacement
            with self.subTest(field=field):
                with mock.patch.object(
                    sound_release,
                    "read_json",
                    side_effect=lambda path, document=altered: (
                        document
                        if path == sound_release.LICENSE_REVIEWS
                        else original_read_json(path)
                    ),
                ):
                    with self.assertRaisesRegex(sound_release.ReleaseError, "source manifest is stale"):
                        sound_release.validate_manifest(self.manifest)

    def test_per_asset_license_review_requires_retrievable_immutable_evidence(self) -> None:
        review = {
            "logical_path": "effects/example.ogg", "source_sha256": "a" * 64,
            "notice_sha256": "b" * 64, "spdx_expression": "CC0-1.0",
            "reviewed_by": "reviewer", "reviewed_at": "2026-08-10T00:00:00Z",
            "evidence": {"locator": "evidence/README.md", "sha256": "7fabbf69efe3dba33656e9a9852c70edee2072e9a4ea772a4c1ca91a613b121a", "notes": "schema verification fixture only"},
        }
        document = {"$schema": "../schemas/license-reviews-v1.schema.json", "schema_version": 1, "reviews": [review]}
        original_read_json = sound_release.read_json
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: document if path == sound_release.LICENSE_REVIEWS else original_read_json(path)):
            self.assertIn("effects/example.ogg", sound_release.checked_license_reviews())
        broken = copy.deepcopy(document)
        broken["reviews"][0]["evidence"].pop("locator")
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: broken if path == sound_release.LICENSE_REVIEWS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "required"):
                sound_release.checked_license_reviews()
        missing = copy.deepcopy(document)
        missing["reviews"][0]["evidence"]["locator"] = "evidence/missing.txt"
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: missing if path == sound_release.LICENSE_REVIEWS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "missing"):
                sound_release.checked_license_reviews()
        noncanonical = copy.deepcopy(document)
        noncanonical["reviews"][0]["reviewed_at"] = "2026-8-1T0:0:0Z"
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: noncanonical if path == sound_release.LICENSE_REVIEWS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "non-canonical"):
                sound_release.checked_license_reviews()

    def test_tracker_durations_are_bound_to_pinned_measurements(self) -> None:
        ledger = json.loads(sound_release.TRACKER_DURATIONS.read_text())
        self.assertEqual(sound_release.sha256(sound_release.TOOLCHAIN), ledger["toolchain_sha256"])
        trackers = {entry["logical_path"]: entry for entry in ledger["entries"]}
        self.assertEqual(17, len(trackers))
        for logical, entry in trackers.items():
            self.assertEqual(sound_release.sha256(ROOT / logical), entry["source_sha256"])
            self.assertEqual(entry["duration_seconds"], self.assets[logical]["source"]["duration_seconds"])

    def test_tracker_duration_ledger_rejects_duplicate_and_stale_entries(self) -> None:
        ledger = json.loads(sound_release.TRACKER_DURATIONS.read_text())
        original_read_json = sound_release.read_json
        duplicate = copy.deepcopy(ledger)
        duplicate["entries"].append(copy.deepcopy(duplicate["entries"][0]))
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: duplicate if path == sound_release.TRACKER_DURATIONS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "duplicate"):
                sound_release.checked_tracker_durations()
        stale = copy.deepcopy(ledger)
        stale["entries"].append({
            "logical_path": "background/removed-stale.mod",
            "source_sha256": "0" * 64,
            "duration_seconds": 1.0,
        })
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: stale if path == sound_release.TRACKER_DURATIONS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "stale background/removed-stale.mod"):
                sound_release.checked_tracker_durations()

    def test_project_schemas_are_versioned_and_unknown_fields_fail(self) -> None:
        for name in (
            "source-assets-v1.schema.json", "runtime-manifest-v1.schema.json",
            "audio-toolchain-v1.schema.json", "fixture-plan-v1.schema.json",
            "vorbis-quality-reviews-v1.schema.json", "license-reviews-v1.schema.json",
            "tracker-durations-v1.schema.json",
        ):
            self.assertEqual(f"https://atrinik.org/schemas/sound/{name}", sound_release.checked_schema(name)["$id"])
        drifted = copy.deepcopy(self.manifest)
        drifted["unexpected"] = True
        with self.assertRaisesRegex(sound_release.ReleaseError, "schema"):
            sound_release.validate_manifest(drifted, compare_generated=False)

    def test_current_source_asset_is_runtime_schema_compatible(self) -> None:
        toolchain = sound_release.checked_toolchain()
        asset = copy.deepcopy(next(iter(self.assets.values())))
        asset["output"] = {
            "sha256": "a" * 64,
            "size_bytes": 1,
            "codec": "opus",
            "container": "ogg",
            "channels": asset["render"]["channels"],
            "sample_rate": 48000,
            "duration_seconds": asset["source"]["duration_seconds"],
            "peak": 0.5,
            "rms_dbfs": -12.0,
            "clipping": False,
            "rendered_pcm": {
                "sample_rate": 48000,
                "channels": asset["render"]["channels"],
                "duration_seconds": asset["source"]["duration_seconds"],
                "peak": 0.5,
                "rms_dbfs": -12.0,
                "clipping": False,
                "input_peak": 0.5,
                "input_clipping": False,
                "applied_gain_db": 0.0,
            },
        }
        runtime_manifest = {
            "$schema": "schemas/runtime-manifest-v1.schema.json",
            "schema_version": 1,
            "release_tag": "v1.2.3",
            "source_commit": "b" * 40,
            "source_tree": "c" * 40,
            "fixture_only": True,
            "source_size_bytes": 1,
            "runtime_size_bytes": 1,
            "quality_budget": toolchain["quality_budget"],
            "tool_versions": {
                name: "test"
                for name in ("ffmpeg", "timidity", "openmpt123", "opusenc", "opusinfo", "sdl3_mixer_probe")
            },
            "toolchain_sha256": sound_release.sha256(sound_release.TOOLCHAIN),
            "assets": [asset],
        }
        sound_release.validate_runtime_manifest(runtime_manifest)

    def test_vorbis_and_midi_metadata_are_parsed_without_legacy_sidecars(self) -> None:
        vorbis = sound_release.ogg_vorbis_metadata(ROOT / "effects" / "campfire.ogg")
        midi = sound_release.midi_metadata(ROOT / "background" / "restful_town.mid")
        self.assertIn(vorbis.channels, (1, 2))
        self.assertGreater(vorbis.sample_rate, 0)
        self.assertGreater(vorbis.duration_seconds, 0)
        self.assertGreater(midi.duration_seconds, 0)

    def test_toolchain_is_pinned_and_records_instrument_output_permission(self) -> None:
        toolchain = sound_release.checked_toolchain()
        self.assertRegex(toolchain["apt_snapshot"], r"snapshot\.ubuntu\.com/ubuntu/[0-9]{8}T[0-9]{6}Z$")
        self.assertRegex(toolchain["build_image"]["image"], r"@sha256:[0-9a-f]{64}$")
        self.assertTrue(toolchain["instrument_bank"]["recording_distribution_permission"])
        probe = toolchain["tools"]["sdl3_mixer_probe"]
        self.assertEqual(
            sound_release.sha256(ROOT / probe["source_path"]),
            probe["source_sha256"],
        )
        for contract in toolchain["tools"].values():
            self.assertTrue(contract["version_pattern"])
        for name, contract in toolchain["tools"].items():
            if name != "sdl3_mixer_probe":
                self.assertRegex(contract["installed_sha256"], r"^[0-9a-f]{64}$")

    def test_full_runtime_build_refuses_partial_corpus_before_tool_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(sound_release.ReleaseError, "505 release findings"):
                sound_release.build_runtime("v1.2.3", Path(temporary), fixtures=False)

    def test_full_runtime_build_rejects_dirty_release_input(self) -> None:
        completed = type("Completed", (), {"stdout": " M background/fireside.mid\n"})()
        with mock.patch.object(sound_release, "run", return_value=completed):
            with self.assertRaisesRegex(sound_release.ReleaseError, "not clean"):
                sound_release.ensure_clean_release_input()

    def test_full_runtime_build_requires_host_attestation_without_git(self) -> None:
        with mock.patch.object(sound_release, "run", side_effect=sound_release.ReleaseError("Git unavailable")):
            with mock.patch.dict(sound_release.os.environ, {}, clear=True):
                with self.assertRaisesRegex(sound_release.ReleaseError, "host-validated input attestation"):
                    sound_release.ensure_clean_release_input()
            with mock.patch.dict(sound_release.os.environ, {"ATRINIK_RELEASE_INPUT_ATTESTED": "1"}, clear=True):
                sound_release.ensure_clean_release_input()

    def test_publisher_fails_closed_when_host_status_is_dirty_or_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake_git = Path(temporary) / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = rev-parse ]; then\n"
                "  case \"$2\" in\n"
                "    *tree*) printf '%040d\\n' 0 ;;\n"
                "    *) printf '%040d\\n' 1 ;;\n"
                "  esac\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = status ]; then\n"
                "  if [ \"$FAKE_GIT_STATUS\" = fail ]; then exit 7; fi\n"
                "  printf ' M background/fireside.mid\\n'\n"
                "  exit 0\n"
                "fi\n"
                "exit 9\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            for status, diagnostic in (("fail", "cannot verify"), ("dirty", "not clean")):
                with self.subTest(status=status):
                    environment = dict(os.environ, PATH=f"{temporary}:{os.environ['PATH']}", FAKE_GIT_STATUS=status)
                    completed = subprocess.run(
                        [str(ROOT / "tools" / "build-release-assets.sh"), "0.0.0"],
                        cwd=ROOT,
                        env=environment,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self.assertNotEqual(0, completed.returncode)
                    self.assertIn(diagnostic, completed.stderr)

    def test_host_attestation_covers_git_only_checks_but_not_bytes(self) -> None:
        evidence = {
            "locator": "evidence/README.md",
            "sha256": "7fabbf69efe3dba33656e9a9852c70edee2072e9a4ea772a4c1ca91a613b121a",
        }
        with mock.patch.dict(sound_release.os.environ, {"ATRINIK_RELEASE_INPUT_ATTESTED": "1"}, clear=True):
            with mock.patch.object(sound_release, "run", side_effect=sound_release.ReleaseError("Git unavailable")):
                sound_release.ensure_sources_tracked(sound_release.discover_sources())
                sound_release.verify_review_evidence(evidence, "schema fixture")
                sound_release.verify_release_tag("v1.2.3", "a" * 40, "b" * 40)
        with mock.patch.dict(sound_release.os.environ, {}, clear=True):
            with mock.patch.object(sound_release, "run", side_effect=sound_release.ReleaseError("Git unavailable")):
                with self.assertRaisesRegex(sound_release.ReleaseError, "tag cannot be verified"):
                    sound_release.verify_release_tag("v1.2.3", "a" * 40, "b" * 40)
        git_available = type("Completed", (), {"stdout": "true\n"})()
        with mock.patch.dict(sound_release.os.environ, {"ATRINIK_RELEASE_INPUT_ATTESTED": "1"}, clear=True):
            with mock.patch.object(sound_release, "run", side_effect=[sound_release.ReleaseError("tag missing"), git_available]):
                with self.assertRaisesRegex(sound_release.ReleaseError, "tag cannot be verified"):
                    sound_release.verify_release_tag("v1.2.3", "a" * 40, "b" * 40)
        wrong = copy.deepcopy(evidence)
        wrong["sha256"] = "0" * 64
        with mock.patch.dict(sound_release.os.environ, {"ATRINIK_RELEASE_INPUT_ATTESTED": "1"}, clear=True):
            with self.assertRaisesRegex(sound_release.ReleaseError, "hash mismatch"):
                sound_release.verify_review_evidence(wrong, "schema fixture")

    def test_review_candidate_is_nonpublishing_and_license_gated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            arguments = type("Arguments", (), {"logical_path": "background/banrril.mid", "output_directory": temporary})()
            with self.assertRaisesRegex(sound_release.ReleaseError, "passed per-asset license review"):
                sound_release.command_build_review_candidate(arguments)


class DeterministicArchiveTests(unittest.TestCase):
    def test_tree_checksums_are_sorted_and_cover_every_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "z.txt").write_bytes(b"z")
            (root / "nested" / "a.txt").write_bytes(b"a")
            sound_release.write_tree_checksums(root)
            self.assertEqual(
                ["nested/a.txt", "z.txt"],
                [line.split("  ", 1)[1] for line in (root / "SHA256SUMS").read_text().splitlines()],
            )

    def test_full_scale_pcm_is_deterministically_attenuated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clipped.wav"
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 48000, 3, "NONE", "not compressed"))
                output.writeframes(struct.pack("<3h", -32768, 0, 32767))
            result = sound_release.attenuate_clipped_wave(path, -2.0)
            self.assertTrue(result["input_clipping"])
            self.assertFalse(result["clipping"])
            self.assertLess(result["applied_gain_db"], 0)

    def test_near_full_scale_pcm_gets_encoder_headroom(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "near-full-scale.wav"
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 48000, 3, "NONE", "not compressed"))
                output.writeframes(struct.pack("<3h", -32500, 0, 32500))
            result = sound_release.attenuate_clipped_wave(path, -2.0)
            self.assertFalse(result["input_clipping"])
            self.assertFalse(result["clipping"])
            self.assertLessEqual(result["peak"], 10 ** (-2.0 / 20))
            self.assertLess(result["applied_gain_db"], 0)
    def test_archive_bytes_and_metadata_are_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "input"
            root.mkdir()
            (root / "z.txt").write_text("last\n", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "a.txt").write_text("first\n", encoding="utf-8")
            first = Path(temporary) / "first.tar.gz"
            second = Path(temporary) / "second.tar.gz"
            sound_release.deterministic_archive(root, first, "fixture", 1_700_000_000)
            sound_release.deterministic_archive(root, second, "fixture", 1_700_000_000)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as archive:
                members = archive.getmembers()
                self.assertEqual(
                    ["fixture/nested/a.txt", "fixture/z.txt"],
                    [member.name for member in members],
                )
                for member in members:
                    self.assertEqual(1_700_000_000, member.mtime)
                    self.assertEqual(0, member.uid)
                    self.assertEqual(0, member.gid)
                    self.assertEqual(0o644, member.mode)

    def test_checksum_file_is_sorted_and_covers_every_release_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "z.json").write_bytes(b"z")
            (directory / "a.tar.gz").write_bytes(b"a")
            sound_release.write_checksums(directory)
            lines = (directory / "SHA256SUMS").read_text(encoding="ascii").splitlines()
            self.assertEqual(["a.tar.gz", "z.json"], [line.split("  ", 1)[1] for line in lines])
            self.assertEqual(hashlib.sha256(b"a").hexdigest(), lines[0].split("  ", 1)[0])


if __name__ == "__main__":
    unittest.main()
