from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import unittest
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
        self.assertEqual(393, len(blockers))
        self.assertEqual(
            {"license/provenance": 197, "quality-review": 196},
            {
                category: sum(finding["category"] == category for finding in blockers)
                for category in {finding["category"] for finding in blockers}
            },
        )
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

    def test_duration_drift_is_reconciled(self) -> None:
        restful = self.assets["background/restful_town.mid"]["source"]
        self.assertGreater(restful["duration_seconds"], 0)
        self.assertNotIn("background/fboss.mid", self.assets)
        self.assertNotIn("background/fuego.ogg", self.assets)
        self.assertNotIn("background/toroia.s3m", self.assets)
        self.assertFalse((ROOT / "background" / "durations").exists())

    def test_license_findings_fail_closed(self) -> None:
        self.assertEqual("allowed", self.assets["background/fireside.mid"]["license"]["status"])
        self.assertEqual("allowed", self.assets["effects/campfire.ogg"]["license"]["status"])
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

    def test_allowed_notices_resolve_to_exact_lines_and_license_texts(self) -> None:
        toolchain = sound_release.checked_toolchain()
        for logical, asset in self.assets.items():
            contract = asset["license"]
            if contract["status"] != "allowed":
                continue
            notice_path, line_text = contract["notice_reference"].rsplit(":", 1)
            line = (ROOT / notice_path).read_text(encoding="utf-8").splitlines()[int(line_text) - 1]
            self.assertIn(Path(logical).name, line)
            self.assertEqual(
                contract["license_text_path"],
                toolchain["license_texts"][contract["spdx_expression"]]["archive_path"],
            )

    def test_vorbis_quality_review_is_an_immutable_release_gate(self) -> None:
        vorbis = [asset for asset in self.assets.values() if asset["source"]["codec"] == "vorbis"]
        self.assertEqual(196, len(vorbis))
        self.assertTrue(all(asset["quality_review"]["status"] == "blocked" for asset in vorbis))
        self.assertTrue(all(asset["quality_review"]["source_sha256"] == asset["source"]["sha256"] for asset in vorbis))

    def test_vorbis_and_midi_metadata_are_parsed_without_legacy_sidecars(self) -> None:
        vorbis = sound_release.ogg_vorbis_metadata(ROOT / "effects" / "campfire.ogg")
        midi = sound_release.midi_metadata(ROOT / "background" / "restful_town.mid")
        self.assertIn(vorbis.channels, (1, 2))
        self.assertGreater(vorbis.sample_rate, 0)
        self.assertGreater(vorbis.duration_seconds, 0)
        self.assertGreater(midi.duration_seconds, 0)

    def test_toolchain_is_pinned_and_records_instrument_output_permission(self) -> None:
        toolchain = sound_release.checked_toolchain()
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
            with self.assertRaisesRegex(sound_release.ReleaseError, "393 release findings"):
                sound_release.build_runtime("v1.2.3", Path(temporary), fixtures=False)


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
