from __future__ import annotations

import hashlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
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
        self.assertEqual(472, len(blockers))
        self.assertEqual(
            {"license/provenance": 276, "quality-review": 196},
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
        self.assertEqual("blocked", self.assets["background/aa_arofl.xm"]["license"]["status"])
        self.assertIn("per-asset license review", self.assets["background/aa_arofl.xm"]["license"]["blocking_finding"])
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
        self.assertEqual(69, candidates)
        self.assertEqual(63, allowed)

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

    def test_piano_approvals_bind_archived_first_party_grants_and_attribution(self) -> None:
        catalog = sound_release.notice_catalog(ROOT / "background")
        reviews = sound_release.checked_license_reviews()
        attributed = {
            filename for filename, notice in catalog.items()
            if "source: https://www.piano-midi.de/" in notice["text"]
        }
        self.assertEqual(25, len(attributed))
        evidence = ROOT / "evidence" / "captures" / "piano-midi-de-copy-20160409000057.html"
        self.assertEqual(
            "9675b087f9cf38bba94c7edd3ea0827fb13d42452168a453f6a3823d58603078",
            sound_release.sha256(evidence),
        )
        for filename in attributed:
            logical_path = f"background/{filename}"
            notice = catalog[filename]
            with self.subTest(logical_path=logical_path):
                self.assertIn("supplied title:", notice["text"])
                self.assertIn("Copyright", notice["text"])
                self.assertIn("source: https://www.piano-midi.de/", notice["text"])
                self.assertIn("Atrinik modification (2026-08-10): MIDI rendered to Opus", notice["text"])
                self.assertEqual("allowed", self.assets[logical_path]["license"]["status"])
                self.assertEqual("CC-BY-SA-3.0-DE", self.assets[logical_path]["license"]["spdx_expression"])
                self.assertEqual(
                    [{
                        "locator": "evidence/captures/piano-midi-de-copy-20160409000057.html",
                        "sha256": "9675b087f9cf38bba94c7edd3ea0827fb13d42452168a453f6a3823d58603078",
                    }],
                    reviews[logical_path]["evidence"]["artifacts"],
                )

    def test_game_game_approvals_bind_first_party_archive_and_attribution(self) -> None:
        filenames = {
            "battle.mid", "endless_sands.mid", "game_over.mid", "gg.mid", "gg2.mid",
            "green_forest.mid", "high_mountains.mid", "interlude.mid", "lava_city.mid",
            "level_win.mid", "pirates.mid", "running_wild.mid", "ship.mid", "tethanus.mid",
            "the_end.mid", "underground.mid", "vonstantine.mid",
        }
        catalog = sound_release.notice_catalog(ROOT / "background")
        reviews = sound_release.checked_license_reviews()
        artifacts = [
            {
                "locator": "evidence/captures/metaruka-game-game-20190826013953.html",
                "sha256": "329b5abf485654b2e5c14674008000d50fab9fa92a53435643e0508eedc91c19",
            },
            {
                "locator": "evidence/captures/opengameart-game-game-20100909174726.html",
                "sha256": "7660f3f9d46671f0f18e167c7ef3e65876766ac3ecc300325e49123d0a0f8b70",
            },
        ]
        for filename in filenames:
            logical_path = f"background/{filename}"
            with self.subTest(filename=filename):
                notice = catalog[filename]["text"]
                self.assertIn("author: Max McCracken (Metaruka; submitted as maxstack)", notice)
                self.assertIn("work: Game-Game", notice)
                self.assertIn("license: CC-BY-SA-3.0", notice)
                self.assertIn("Atrinik modification (2026-08-10): original MIDI rendered to Opus", notice)
                self.assertEqual("allowed", self.assets[logical_path]["license"]["status"])
                self.assertEqual("CC-BY-SA-3.0", self.assets[logical_path]["license"]["spdx_expression"])
                self.assertEqual(artifacts, reviews[logical_path]["evidence"]["artifacts"])

    def test_notice_hash_preserves_exact_packaged_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "background"
            directory.mkdir()
            license_path = directory / "LICENSE"
            license_path.write_text("Example - CC0:\n    example.ogg (notice)\n", encoding="utf-8")
            original = sound_release.notice_catalog(directory)["example.ogg"]["text"]
            license_path.write_text("Example - CC0:\n    example.ogg (notice)  \n", encoding="utf-8")
            drifted = sound_release.notice_catalog(directory)["example.ogg"]["text"]
            self.assertNotEqual(original, drifted)
            self.assertNotEqual(
                hashlib.sha256(original.encode()).digest(),
                hashlib.sha256(drifted.encode()).digest(),
            )
            license_path.write_bytes(b"Example - CC0:\r\n    example.ogg (notice)\r\n")
            crlf = sound_release.notice_catalog(directory)["example.ogg"]["text"]
            self.assertNotEqual(original, crlf)

    def test_approved_gpl_notices_preserve_authors_and_modification_dates(self) -> None:
        catalog = sound_release.notice_catalog(ROOT / "background")
        expectations = {
            "piano.mid": (
                "supplied title: “Rêverie” by Claude Debussy 1890",
                "Sylvain Beucler",
                "Copyright (C) 2008 Sylvain Beucler",
            ),
            "run_for_your_life.mid": ("Tistou Blomberg", "supplied title: Excitement! Run for your life"),
            "the_fast_route.mid": ("musician: mimm", "supplied title: The Fast Route", "omitted channel 5"),
            "ultimate_run.mid": ("Tistou Blomberg", "supplied title: Ultimate run"),
        }
        for filename, required in expectations.items():
            with self.subTest(filename=filename):
                notice = catalog[filename]["text"]
                self.assertEqual("allowed", self.assets[f"background/{filename}"]["license"]["status"])
                for text in required:
                    self.assertIn(text, notice)
                self.assertIn("Atrinik modification (2026-08-10): MIDI rendered to Opus", notice)

    def test_mamoru_approvals_preserve_author_source_and_modification(self) -> None:
        catalog = sound_release.notice_catalog(ROOT / "background")
        filenames = {
            "banrril.mid", "burnt_forest.mid", "burnt_forest2.mid", "chether.mid",
            "denkash.mid", "denkash-finale.mid", "endurance.mid", "essilda-finale.mid",
            "kaitindam.mid", "tutorialisland.mid",
        }
        for filename in filenames:
            with self.subTest(filename=filename):
                notice = catalog[filename]["text"]
                self.assertEqual("allowed", self.assets[f"background/{filename}"]["license"]["status"])
                self.assertIn("author: Edwin “Mamoru” Miltenburg", notice)
                self.assertIn(f"source: atrinik/sound background/{filename} at c2b8af8426b6275b345fa906348db51ca16336f5", notice)
                self.assertIn("Atrinik modification (2026-08-10): MIDI rendered to Opus", notice)

    def test_opengameart_cc0_approvals_bind_preserved_first_party_pages(self) -> None:
        catalog = sound_release.notice_catalog(ROOT / "background")
        expected = {
            "evil_temple.ogg": "Brandon Morris",
            "lost_in_meadows.ogg": "Augmentality",
            "running.ogg": "Augmentality (Brandon Morris)",
            "sewer_rats.ogg": "HaelDB",
        }
        reviews = sound_release.checked_license_reviews()
        for filename, author in expected.items():
            logical_path = f"background/{filename}"
            with self.subTest(filename=filename):
                notice = catalog[filename]["text"]
                self.assertEqual("allowed", self.assets[logical_path]["license"]["status"])
                self.assertIn(f"author: {author}", notice)
                self.assertIn("Atrinik modification (2026-08-10): historical Vorbis encoding converted to Opus", notice)
                self.assertTrue(str(reviews[logical_path]["evidence"]["locator"]).endswith(".html"))
                self.assertEqual(
                    [{
                        "locator": "evidence/opengameart-brandon-morris-backgrounds.md",
                        "sha256": "3d028b3abc8bd66d567ab4dba532ee6386431a8cf3b34fa014ef77ea4f67a43d",
                    }],
                    reviews[logical_path]["evidence"]["artifacts"],
                )

    def test_oneoff_vorbis_approvals_preserve_first_party_grants_and_changes(self) -> None:
        catalog = sound_release.notice_catalog(ROOT / "background")
        reviews = sound_release.checked_license_reviews()
        required = {
            "crystal_falls.ogg": ("author: Écrivain", "official WAV encoded to Vorbis"),
            "hull_et_belle.ogg": ("author: Gobusto", "license: CC-BY-SA-3.0"),
            "frankie.ogg": ("(c) copyright Blender Foundation | apricot.blender.org", "license: CC-BY-3.0"),
        }
        for filename, fields in required.items():
            logical_path = f"background/{filename}"
            with self.subTest(filename=filename):
                notice = catalog[filename]["text"]
                self.assertEqual("allowed", self.assets[logical_path]["license"]["status"])
                for field in fields:
                    self.assertIn(field, notice)
                self.assertIn("Atrinik modification (2026-08-10)", notice)
                self.assertEqual(
                    [{
                        "locator": "evidence/oga-yofrankie-backgrounds.md",
                        "sha256": "a41212885200703f343feb922e11a6799c0cb47a261f0a97744c7346565b1544",
                    }],
                    reviews[logical_path]["evidence"]["artifacts"],
                )

    def test_exact_stendhal_tracks_preserve_storyteller_but_remain_blocked(self) -> None:
        reviewed_paths = {
            "background/deep_forest.ogg", "background/dungeon_entrance.ogg",
            "background/magical_tower.ogg", "background/mystical_aura.ogg",
            "background/new_hope.ogg", "background/sacred_moments.ogg",
        }
        catalog = sound_release.notice_catalog(ROOT / "background")
        for logical_path in reviewed_paths:
            notice = catalog[Path(logical_path).name]
            with self.subTest(logical_path=logical_path):
                self.assertIn("author: Storyteller", notice["text"])
                self.assertIn("arianne/stendhal", notice["text"])
                self.assertIn("Atrinik modification: Vorbis converted to Opus", notice["text"])
                self.assertEqual("blocked", self.assets[logical_path]["license"]["status"])
                self.assertIsNone(self.assets[logical_path]["license"]["spdx_expression"])

    def test_vorbis_quality_review_is_an_immutable_release_gate(self) -> None:
        vorbis = [asset for asset in self.assets.values() if asset["source"]["codec"] == "vorbis"]
        self.assertEqual(196, len(vorbis))
        self.assertTrue(all(asset["quality_review"]["status"] == "blocked" for asset in vorbis))
        self.assertTrue(all(asset["quality_review"]["source_sha256"] == asset["source"]["sha256"] for asset in vorbis))

    def test_validation_dispatches_live_attestations_with_ci_permission(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
        publisher = (ROOT / "tools" / "build-release-assets.sh").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"(?m)^  issues: read$")
        self.assertEqual(2, workflow.count("fetch-depth: 0"))
        self.assertIn("--env GH_TOKEN", publisher)
        reviews = {"background/example.ogg": {"evidence": {
            "artifact_locator": "evidence/review.json",
            "artifact_sha256": "a" * 64,
            "github_attestation_url": "https://github.com/atrinik/sound/issues/21#issuecomment-123",
        }}}
        with mock.patch.object(sound_release, "checked_manifest", return_value={"audio_source_count": 0}), \
                mock.patch.object(sound_release, "validate_manifest", return_value=[]), \
                mock.patch.object(sound_release, "checked_quality_reviews", return_value=reviews), \
                mock.patch.object(sound_release, "verify_quality_review_attestations") as verify, \
                mock.patch.object(sound_release, "checked_toolchain"), \
                mock.patch.object(sound_release, "checked_fixture_plan"):
            sound_release.command_validate(type("Arguments", (), {})())
        verify.assert_called_once_with(reviews)

    @mock.patch.object(sound_release, "verify_quality_review_source_tree")
    @mock.patch.object(sound_release, "quality_review_bundle_contract")
    def test_quality_review_rejects_malformed_or_mutable_evidence(
        self, _bundle_contract: mock.Mock, _source_tree: mock.Mock,
    ) -> None:
        entry = {
            "logical_path": "effects/example.ogg", "status": "passed", "source_sha256": "a" * 64,
            "toolchain_sha256": sound_release.sha256(sound_release.TOOLCHAIN), "output_sha256": "b" * 64,
            "reviewed_by": "reviewer", "reviewed_at": "2026-08-10T00:00:00Z",
            "evidence": {"method": "critical-listening", "artifact_locator": "evidence/README.md", "artifact_sha256": "7fabbf69efe3dba33656e9a9852c70edee2072e9a4ea772a4c1ca91a613b121a", "github_attestation_url": "https://github.com/atrinik/sound/issues/22#issuecomment-123", "notes": "schema verification fixture only"},
        }
        artifact = {
            "$schema": "https://atrinik.org/schemas/sound/critical-listening-review-v1.schema.json",
            "schema_version": 1, "non_publishing": True,
            "reviewed_by": "reviewer", "reviewed_at": "2026-08-10T00:00:00Z",
            "source_tree": "a" * 40,
            "review_input_sha256": "c" * 64,
            "toolchain_sha256": sound_release.sha256(sound_release.TOOLCHAIN),
            "review_bundle_sha256": "d" * 64,
            "worksheet_contract_sha256": "e" * 64,
            "procedure": {"headphones_checked": True, "representative_speakers_checked": True, "loop_boundaries_checked": True},
            "reviews": [{
                "logical_path": "effects/example.ogg", "source_sha256": "a" * 64,
                "output_sha256": "b" * 64,
                "review_evidence_path": "candidates/effects/example.ogg/review-evidence.json",
                "candidate_evidence": {
                    "schema_version": 1, "logical_path": "effects/example.ogg", "source_sha256": "a" * 64,
                    "toolchain_sha256": sound_release.sha256(sound_release.TOOLCHAIN), "output_sha256": "b" * 64,
                    "generated_path": "audio/effects/example.ogg.opus", "tool_versions": {}, "measurements": {}, "non_publishing": True,
                },
                "source_playback_completed": True, "candidate_playback_completed": True,
                "artifacts": "No artifacts detected.", "noise_floor": "Noise floor matched.",
                "duration_tail": "Duration and tail matched.", "loop_boundary": "Loop boundary matched.",
                "verdict": "passed",
            }],
        }
        document = {"$schema": "../schemas/vorbis-quality-reviews-v2.schema.json", "schema_version": 2, "reviews": [entry]}
        original_read_json = sound_release.read_json
        def fixture_read(path: Path, quality_document: object = document) -> object:
            if path == sound_release.QUALITY_REVIEWS:
                return quality_document
            if path == ROOT / "evidence/README.md":
                return artifact
            return original_read_json(path)
        with mock.patch.object(sound_release, "read_json", side_effect=fixture_read):
            self.assertIn("effects/example.ogg", sound_release.checked_quality_reviews())
        failed_artifact = copy.deepcopy(artifact)
        failed_artifact["reviews"][0]["verdict"] = "failed"
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: failed_artifact if path == ROOT / "evidence/README.md" else fixture_read(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "does not match passed artifact"):
                sound_release.checked_quality_reviews()
        broken = copy.deepcopy(document)
        broken["reviews"][0]["reviewed_at"] = "yesterday"
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: fixture_read(path, broken)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "timestamp"):
                sound_release.checked_quality_reviews()
        invalid_reviewer = copy.deepcopy(document)
        invalid_reviewer["reviews"][0]["reviewed_by"] = "a--b"
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: fixture_read(path, invalid_reviewer)):
            with self.assertRaises(sound_release.ReleaseError):
                sound_release.checked_quality_reviews()
        wrong_hash = copy.deepcopy(document)
        wrong_hash["reviews"][0]["evidence"]["artifact_sha256"] = "0" * 64
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: fixture_read(path, wrong_hash)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "hash mismatch"):
                sound_release.checked_quality_reviews()

    def test_review_and_encoding_contracts_detect_immutable_input_drift(self) -> None:
        reviewed = json.loads((ROOT / "manifests" / "license-reviews.json").read_text())
        self.assertEqual(63, len(reviewed["reviews"]))
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
            "evidence": {
                "locator": "evidence/README.md",
                "sha256": "7fabbf69efe3dba33656e9a9852c70edee2072e9a4ea772a4c1ca91a613b121a",
                "notes": "schema verification fixture only",
                "artifacts": [{
                    "locator": "evidence/freedink-backgrounds.md",
                    "sha256": "9c5db5b1d82ddcd2a3294261154b0349ef7f3a824afa25ef2c49f69fcde03c92",
                }],
            },
        }
        document = {"$schema": "../schemas/license-reviews-v2.schema.json", "schema_version": 2, "reviews": [review]}
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
        corrupted_artifact = copy.deepcopy(document)
        corrupted_artifact["reviews"][0]["evidence"]["artifacts"][0]["sha256"] = "0" * 64
        with mock.patch.object(sound_release, "read_json", side_effect=lambda path: corrupted_artifact if path == sound_release.LICENSE_REVIEWS else original_read_json(path)):
            with self.assertRaisesRegex(sound_release.ReleaseError, "hash mismatch"):
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
            "vorbis-quality-reviews-v1.schema.json", "vorbis-quality-reviews-v2.schema.json",
            "critical-listening-review-v1.schema.json", "license-reviews-v1.schema.json",
            "license-reviews-v2.schema.json",
            "tracker-durations-v1.schema.json",
        ):
            self.assertEqual(f"https://atrinik.org/schemas/sound/{name}", sound_release.checked_schema(name)["$id"])
        legacy_pattern = sound_release.checked_schema("vorbis-quality-reviews-v1.schema.json")["properties"]["reviews"]["items"]["properties"]["reviewed_by"]["pattern"]
        current_pattern = sound_release.checked_schema("vorbis-quality-reviews-v2.schema.json")["properties"]["reviews"]["items"]["properties"]["reviewed_by"]["pattern"]
        self.assertIsNotNone(re.fullmatch(legacy_pattern, "a--b"))
        self.assertIsNone(re.fullmatch(current_pattern, "a--b"))
        drifted = copy.deepcopy(self.manifest)
        drifted["unexpected"] = True
        with self.assertRaisesRegex(sound_release.ReleaseError, "schema"):
            sound_release.validate_manifest(drifted, compare_generated=False)

    def test_current_source_asset_is_runtime_schema_compatible(self) -> None:
        toolchain = sound_release.checked_toolchain()
        logical_path = "background/crystal_falls.ogg"
        review = {
            "logical_path": logical_path,
            "status": "passed",
            "source_sha256": self.assets[logical_path]["source"]["sha256"],
            "toolchain_sha256": sound_release.sha256(sound_release.TOOLCHAIN),
            "output_sha256": "a" * 64,
            "reviewed_by": "reviewer",
            "reviewed_at": "2026-08-10T12:00:00Z",
            "evidence": {
                "method": "critical-listening",
                "artifact_locator": "evidence/review.json",
                "artifact_sha256": "d" * 64,
                "github_attestation_url": "https://github.com/atrinik/sound/issues/21#issuecomment-123",
                "notes": "Complete critical-listening evidence.",
            },
        }
        projected_review = sound_release.published_quality_review(review)
        self.assertNotIn("github_attestation_url", projected_review["evidence"])
        self.assertIn("Quality-review record SHA-256:", projected_review["evidence"]["notes"])
        self.assertIn(review["evidence"]["github_attestation_url"], projected_review["evidence"]["notes"])
        source_manifest = copy.deepcopy(self.manifest)
        source_asset = next(
            item for item in source_manifest["assets"] if item["logical_path"] == logical_path
        )
        source_asset["quality_review"] = projected_review
        sound_release.validate_manifest(source_manifest, compare_generated=False)
        asset = copy.deepcopy(source_asset)
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
            with self.assertRaisesRegex(sound_release.ReleaseError, "472 release findings"):
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
            arguments = type("Arguments", (), {"logical_path": "background/aa_arofl.xm", "output_directory": temporary})()
            with self.assertRaisesRegex(sound_release.ReleaseError, "passed per-asset license review"):
                sound_release.command_build_review_candidate(arguments)

    @mock.patch.object(sound_release, "verify_review_bundle_candidates")
    def test_review_bundle_is_self_contained_and_selects_only_eligible_vorbis(
        self, _verify_candidates: mock.Mock,
    ) -> None:
        expected = {
            "background/crystal_falls.ogg", "background/evil_temple.ogg",
            "background/frankie.ogg", "background/hull_et_belle.ogg",
            "background/lost_in_meadows.ogg", "background/running.ogg",
            "background/sewer_rats.ogg",
        }

        def fake_convert(asset: dict[str, object], output_directory: Path, _toolchain: dict[str, object]) -> dict[str, object]:
            output_path = output_directory / str(asset["generated_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"candidate:{asset['logical_path']}".encode()
            output_path.write_bytes(payload)
            return {"output": {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "rendered_pcm": {"applied_gain_db": 0.0},
            }}

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "review"
            arguments = type("Arguments", (), {"output_directory": output})()
            with mock.patch.object(sound_release, "verify_toolchain", return_value={"opusenc": "fixture"}), mock.patch.object(sound_release, "convert_asset", side_effect=fake_convert):
                sound_release.command_build_review_bundle(arguments)
            bundle = json.loads((output / "review-bundle.json").read_text())
            self.assertTrue(bundle["non_publishing"])
            self.assertEqual(expected, {asset["logical_path"] for asset in bundle["assets"]})
            expected_inputs = [self.assets[path] for path in sorted(expected)]
            self.assertEqual(sound_release.quality_review_input_sha256(expected_inputs), bundle["review_input_sha256"])
            index = (output / "index.html").read_text()
            self.assertIn("A: source", index)
            self.assertIn("B: candidate", index)
            self.assertIn("Candidate gain:", index)
            self.assertIn("Source playback is level-matched", index)
            self.assertIn("Use a valid GitHub username without a leading @.", index)
            self.assertIn("^(?!.*--)[A-Za-z0-9]", index)
            self.assertIn("let playingAudio=null", index)
            self.assertIn("audio.played.length", index)
            self.assertIn("if(start>coveredUntil+0.25)return false", index)
            self.assertIn("seeking cannot replace full playback", index)
            field_policy_start = index.index("const reviewFieldComplete=")
            field_policy_end = index.index(";\nfor(const section", field_policy_start) + 1
            field_policy = index[field_policy_start:field_policy_end]
            behavior = subprocess.run(
                ["node", "--eval", field_policy + """
if (!reviewFieldComplete('verdict','passed')) process.exit(1);
if (!reviewFieldComplete('verdict','failed')) process.exit(2);
if (reviewFieldComplete('verdict','')) process.exit(3);
if (!reviewFieldComplete('artifacts','12345678')) process.exit(4);
if (reviewFieldComplete('artifacts','1234567')) process.exit(5);
"""],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(0, behavior.returncode, behavior.stderr)
            self.assertIn("critical-listening-review-v1.schema.json", index)
            for asset in bundle["assets"]:
                source = output / asset["source_path"]
                candidate = output / asset["candidate_path"]
                evidence = output / asset["review_evidence_path"]
                self.assertEqual(sound_release.sha256(ROOT / asset["logical_path"]), sound_release.sha256(source))
                self.assertEqual(asset["output_sha256"], sound_release.sha256(candidate))
                self.assertTrue(evidence.is_file())
                self.assertEqual(0.0, asset["candidate_gain_db"])
                self.assertIn(asset["logical_path"], index)
            checksums = (output / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(sorted(checksums, key=lambda line: line.split("  ", 1)[1]), checksums)
            self.assertNotIn("SHA256SUMS", {line.split("  ", 1)[1] for line in checksums})
            result = {
                "$schema": "https://atrinik.org/schemas/sound/critical-listening-review-v1.schema.json",
                "schema_version": 1,
                "non_publishing": True,
                "reviewed_by": "reviewer",
                "reviewed_at": "2026-08-10T12:00:00Z",
                "source_tree": bundle["source_tree"],
                "review_input_sha256": bundle["review_input_sha256"],
                "toolchain_sha256": bundle["toolchain_sha256"],
                "review_bundle_sha256": bundle["contract_sha256"],
                "worksheet_contract_sha256": bundle["worksheet_contract_sha256"],
                "procedure": {
                    "headphones_checked": True,
                    "representative_speakers_checked": True,
                    "loop_boundaries_checked": True,
                },
                "reviews": [{
                    "logical_path": asset["logical_path"],
                    "source_sha256": asset["source_sha256"],
                    "output_sha256": asset["output_sha256"],
                    "review_evidence_path": asset["review_evidence_path"],
                    "candidate_evidence": asset["candidate_evidence"],
                    "source_playback_completed": True,
                    "candidate_playback_completed": True,
                    "artifacts": "No audible codec, tonal, or transient regression.",
                    "noise_floor": "No noise-floor modulation or low-level loss.",
                    "duration_tail": "Complete duration and tail; no truncation.",
                    "loop_boundary": "Loop transition matches the canonical source.",
                    "verdict": "passed",
                } for asset in bundle["assets"]],
            }
            verified_bundle, verified_reviews = sound_release.verify_review_bundle_result(output, result)
            self.assertEqual(bundle, sound_release.quality_review_bundle_contract(result))
            subset_result = copy.deepcopy(result)
            subset_result["reviews"] = subset_result["reviews"][:1]
            with self.assertRaisesRegex(sound_release.ReleaseError, "exact eligible asset set"):
                sound_release.quality_review_bundle_contract(subset_result)
            backdated_subset = copy.deepcopy(result)
            backdated_subset["reviewed_at"] = "2026-08-10T07:40:00Z"
            backdated_subset["reviews"] = backdated_subset["reviews"][:4]
            with self.assertRaisesRegex(sound_release.ReleaseError, "exact eligible asset set"):
                sound_release.quality_review_bundle_contract(backdated_subset)
            forged_snapshot = copy.deepcopy(self.manifest)
            forged_snapshot["assets"] = forged_snapshot["assets"][:-1]
            git_show = subprocess.CompletedProcess([], 0, json.dumps(forged_snapshot), "")
            with tempfile.TemporaryDirectory() as snapshot_directory, \
                    mock.patch.object(sound_release, "git_metadata_available", return_value=True), \
                    mock.patch.object(sound_release, "run", return_value=git_show), \
                    mock.patch.object(sound_release, "archived_repository_tree") as archived:
                archived.return_value.__enter__.return_value = Path(snapshot_directory)
                archived.return_value.__exit__.return_value = False
                with mock.patch.object(sound_release, "build_source_manifest", return_value=self.manifest):
                    with self.assertRaisesRegex(sound_release.ReleaseError, "non-canonical source manifest"):
                        sound_release.review_snapshot_manifest(result)
            duplicate_result = copy.deepcopy(result)
            duplicate = copy.deepcopy(duplicate_result["reviews"][0])
            duplicate["artifacts"] = "Different substantive artifact notes."
            duplicate_result["reviews"].append(duplicate)
            with self.assertRaisesRegex(sound_release.ReleaseError, "duplicate critical-listening result"):
                sound_release.quality_review_bundle_contract(duplicate_result)
            stale_input = copy.deepcopy(result)
            stale_input["review_input_sha256"] = "0" * 64
            with self.assertRaisesRegex(sound_release.ReleaseError, "review-input contract"):
                sound_release.quality_review_bundle_contract(stale_input)
            stale_worksheet = copy.deepcopy(result)
            stale_worksheet["worksheet_contract_sha256"] = "0" * 64
            with self.assertRaisesRegex(sound_release.ReleaseError, "canonical worksheet"):
                sound_release.quality_review_bundle_contract(stale_worksheet)
            introduction = subprocess.CompletedProcess([], 0, "f" * 40 + "\n", "")
            parent = subprocess.CompletedProcess([], 0, "e" * 40 + "\n", "")
            parent_tree = subprocess.CompletedProcess([], 0, result["source_tree"] + "\n", "")
            with mock.patch.object(sound_release, "git_metadata_available", return_value=True), \
                    mock.patch.object(sound_release, "run", side_effect=[introduction, parent, parent_tree]):
                sound_release.verify_quality_review_source_tree(result, "evidence/review.json")
            wrong_tree = subprocess.CompletedProcess([], 0, "0" * 40 + "\n", "")
            with mock.patch.object(sound_release, "git_metadata_available", return_value=True), \
                    mock.patch.object(sound_release, "run", side_effect=[introduction, parent, wrong_tree]):
                with self.assertRaisesRegex(sound_release.ReleaseError, "introduced over its source tree"):
                    sound_release.verify_quality_review_source_tree(result, "evidence/review.json")
            first_review = result["reviews"][0]
            ledger_entry = {
                "output_sha256": first_review["output_sha256"],
                "evidence": {"artifact_locator": "evidence/review.json"},
            }
            with mock.patch.object(sound_release, "checked_critical_listening_result", return_value=result), \
                    mock.patch.object(sound_release, "checked_toolchain", return_value={}), \
                    mock.patch.object(sound_release, "verify_toolchain", return_value={}), \
                    mock.patch.object(sound_release, "write_review_candidate", return_value=first_review["candidate_evidence"]):
                sound_release.verify_quality_review_outputs({first_review["logical_path"]: ledger_entry})
                forged_result = copy.deepcopy(result)
                forged_review = forged_result["reviews"][0]
                forged_review["output_sha256"] = "b" * 64
                forged_review["candidate_evidence"]["output_sha256"] = "b" * 64
                forged_entry = copy.deepcopy(ledger_entry)
                forged_entry["output_sha256"] = "b" * 64
                with mock.patch.object(sound_release, "checked_critical_listening_result", return_value=forged_result):
                    with self.assertRaisesRegex(sound_release.ReleaseError, "deterministic current candidate"):
                        sound_release.verify_quality_review_outputs({first_review["logical_path"]: forged_entry})
            proposed = sound_release.proposed_quality_review_ledger(
                verified_bundle, result, verified_reviews, "evidence/review.json", "c" * 64,
                "https://github.com/atrinik/sound/issues/21#issuecomment-123",
            )
            self.assertEqual(expected, {entry["logical_path"] for entry in proposed["reviews"]})
            failed = copy.deepcopy(result)
            failed["reviews"][0]["verdict"] = "failed"
            failed_bundle, failed_reviews = sound_release.verify_review_bundle_result(output, failed)
            failed_proposal = sound_release.proposed_quality_review_ledger(
                failed_bundle, failed, failed_reviews, "evidence/review.json", "c" * 64,
                "https://github.com/atrinik/sound/issues/21#issuecomment-123",
            )
            self.assertEqual(len(expected) - 1, len(failed_proposal["reviews"]))
            drifted = copy.deepcopy(result)
            drifted["reviews"][0]["output_sha256"] = "0" * 64
            with self.assertRaisesRegex(sound_release.ReleaseError, "does not match bundle"):
                sound_release.verify_review_bundle_result(output, drifted)
            future = copy.deepcopy(result)
            future["reviewed_at"] = "2999-01-01T00:00:00Z"
            with self.assertRaisesRegex(sound_release.ReleaseError, "future"):
                sound_release.verify_review_bundle_result(output, future)
            whitespace = copy.deepcopy(result)
            whitespace["reviews"][0]["artifacts"] = "        "
            with self.assertRaises(sound_release.ReleaseError):
                sound_release.verify_review_bundle_result(output, whitespace)
            incomplete_playback = copy.deepcopy(result)
            incomplete_playback["reviews"][0]["source_playback_completed"] = False
            with self.assertRaises(sound_release.ReleaseError):
                sound_release.verify_review_bundle_result(output, incomplete_playback)
            effect_shape = copy.deepcopy(result)
            effect_shape["reviews"][0]["logical_path"] = "effects/example.ogg"
            effect_shape["reviews"][0]["review_evidence_path"] = "candidates/effects/example.ogg/review-evidence.json"
            sound_release.validate_schema_instance(
                effect_shape, sound_release.checked_schema("critical-listening-review-v1.schema.json"),
            )
            result_hash = "c" * 64
            comment = {
                "html_url": "https://github.com/atrinik/sound/issues/21#issuecomment-123",
                "issue_url": "https://api.github.com/repos/atrinik/sound/issues/21",
                "node_id": "IC_fixture",
                "author_association": "OWNER",
                "user": {"login": "reviewer"},
                "body": sound_release.github_attestation_body(result_hash),
                "created_at": "2026-08-10T12:05:00Z",
                "updated_at": "2026-08-10T12:05:00Z",
            }
            completed = subprocess.CompletedProcess([], 0, json.dumps(comment), "")
            permission = subprocess.CompletedProcess(
                [], 0, json.dumps({"permission": "admin", "role_name": "admin"}), "",
            )
            unedited = subprocess.CompletedProcess(
                [], 0, json.dumps({"data": {"node": {"lastEditedAt": None}}}), "",
            )
            with mock.patch.object(sound_release, "run", side_effect=[completed, unedited, permission]):
                sound_release.checked_github_attestation(
                    "https://github.com/atrinik/sound/issues/21#issuecomment-123", result, result_hash,
                )
                with self.assertRaisesRegex(sound_release.ReleaseError, "asset class"):
                    sound_release.checked_github_attestation(
                        "https://github.com/atrinik/sound/issues/22#issuecomment-123", result, result_hash,
                    )
            wrong_author = copy.deepcopy(comment)
            wrong_author["user"]["login"] = "somebody-else"
            with mock.patch.object(sound_release, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(wrong_author), "")):
                with self.assertRaisesRegex(sound_release.ReleaseError, "does not match"):
                    sound_release.checked_github_attestation(
                        "https://github.com/atrinik/sound/issues/21#issuecomment-123", result, result_hash,
                    )
            read_only = subprocess.CompletedProcess(
                [], 0, json.dumps({"permission": "read", "role_name": "read"}), "",
            )
            with mock.patch.object(sound_release, "run", side_effect=[completed, unedited, read_only]):
                with self.assertRaisesRegex(sound_release.ReleaseError, "write permission"):
                    sound_release.checked_github_attestation(
                        "https://github.com/atrinik/sound/issues/21#issuecomment-123", result, result_hash,
                    )
            edited = copy.deepcopy(comment)
            edited["updated_at"] = "2026-08-10T12:06:00Z"
            with mock.patch.object(sound_release, "run", return_value=
                    subprocess.CompletedProcess([], 0, json.dumps(edited), "")):
                with self.assertRaisesRegex(sound_release.ReleaseError, "comment was edited"):
                    sound_release.checked_github_attestation(
                        "https://github.com/atrinik/sound/issues/21#issuecomment-123", result, result_hash,
                    )
            same_second_edit = subprocess.CompletedProcess(
                [], 0, json.dumps({"data": {"node": {"lastEditedAt": "2026-08-10T12:05:00Z"}}}), "",
            )
            with mock.patch.object(sound_release, "run", side_effect=[completed, same_second_edit]):
                with self.assertRaisesRegex(sound_release.ReleaseError, "comment was edited"):
                    sound_release.checked_github_attestation(
                        "https://github.com/atrinik/sound/issues/21#issuecomment-123", result, result_hash,
                    )
            custom_write = subprocess.CompletedProcess(
                [], 0, json.dumps({"permission": "write", "role_name": "sound-reviewer"}), "",
            )
            with mock.patch.object(sound_release, "run", side_effect=[completed, unedited, custom_write]):
                sound_release.checked_github_attestation(
                    "https://github.com/atrinik/sound/issues/21#issuecomment-123", result, result_hash,
                )
            substituted_root = Path(temporary) / "substituted"
            shutil.copytree(output, substituted_root)
            substituted_bundle = json.loads((substituted_root / "review-bundle.json").read_text())
            substituted_asset = substituted_bundle["assets"][0]
            substituted_source = substituted_root / substituted_asset["source_path"]
            substituted_source.write_bytes(b"substituted source")
            substituted_hash = sound_release.sha256(substituted_source)
            substituted_asset["source_sha256"] = substituted_hash
            substituted_asset["candidate_evidence"]["source_sha256"] = substituted_hash
            substituted_evidence = substituted_root / substituted_asset["review_evidence_path"]
            substituted_evidence.write_bytes(sound_release.canonical_json(substituted_asset["candidate_evidence"]))
            substituted_bundle.pop("contract_sha256")
            substituted_bundle.pop("worksheet_contract_sha256")
            substituted_bundle.pop("worksheet_sha256")
            substituted_bundle = json.loads(sound_release.canonical_json(substituted_bundle))
            substituted_bundle["contract_sha256"] = hashlib.sha256(
                sound_release.canonical_json(substituted_bundle),
            ).hexdigest()
            substituted_bundle["worksheet_contract_sha256"] = sound_release.worksheet_contract_sha256(substituted_bundle)
            substituted_worksheet = sound_release.review_bundle_html(substituted_bundle)
            substituted_bundle["worksheet_sha256"] = hashlib.sha256(substituted_worksheet).hexdigest()
            (substituted_root / "review-bundle.json").write_bytes(sound_release.canonical_json(substituted_bundle))
            (substituted_root / "index.html").write_bytes(substituted_worksheet)
            substituted_result = copy.deepcopy(result)
            substituted_result["reviews"][0]["source_sha256"] = substituted_hash
            substituted_result["reviews"][0]["candidate_evidence"]["source_sha256"] = substituted_hash
            substituted_result["review_bundle_sha256"] = substituted_bundle["contract_sha256"]
            substituted_result["worksheet_contract_sha256"] = substituted_bundle["worksheet_contract_sha256"]
            (substituted_root / "SHA256SUMS").unlink()
            sound_release.write_tree_checksums(substituted_root)
            with self.assertRaisesRegex(sound_release.ReleaseError, "current manifest"):
                sound_release.verify_review_bundle_result(substituted_root, substituted_result)
            symlink_target = Path(temporary) / "symlink-target"
            symlink_target.mkdir()
            bundle_symlink = output / "unexpected-directory-link"
            bundle_symlink.symlink_to(symlink_target, target_is_directory=True)
            with self.assertRaisesRegex(sound_release.ReleaseError, "contains a symlink"):
                sound_release.verify_review_bundle_result(output, result)
            bundle_symlink.unlink()
            canonical_index = (output / "index.html").read_bytes()
            (output / "index.html").write_bytes(canonical_index.replace(
                b"candidate.src=a.candidate_path", b"candidate.src=a.source_path   ",
            ))
            (output / "SHA256SUMS").unlink()
            sound_release.write_tree_checksums(output)
            with self.assertRaisesRegex(sound_release.ReleaseError, "worksheet is not canonical"):
                sound_release.verify_review_bundle_result(output, result)
            (output / "index.html").write_bytes(canonical_index)
            (output / "SHA256SUMS").unlink()
            sound_release.write_tree_checksums(output)
            unsafe_arguments = type("Arguments", (), {
                "bundle_directory": output,
                "evidence_locator": "../review.json",
                "github_attestation_url": "https://github.com/atrinik/sound/issues/21#issuecomment-123",
            })()
            with self.assertRaisesRegex(sound_release.ReleaseError, "repository-owned"):
                sound_release.command_prepare_quality_review(unsafe_arguments)
            first_candidate = output / bundle["assets"][0]["candidate_path"]
            first_candidate.write_bytes(b"tampered")
            with self.assertRaisesRegex(sound_release.ReleaseError, "checksum mismatch"):
                sound_release.verify_review_bundle_result(output, result)
            with self.assertRaisesRegex(sound_release.ReleaseError, "must be empty"):
                sound_release.command_build_review_bundle(arguments)

    def test_review_bundle_reproduces_candidates_in_pinned_toolchain(self) -> None:
        logical_path = "background/example.ogg"
        generated_path = "audio/background/example.ogg.opus"
        evidence = {
            "schema_version": 1,
            "logical_path": logical_path,
            "source_sha256": "a" * 64,
            "toolchain_sha256": sound_release.sha256(sound_release.TOOLCHAIN),
            "output_sha256": hashlib.sha256(b"canonical candidate").hexdigest(),
            "generated_path": generated_path,
            "tool_versions": {"opusenc": "fixture"},
            "measurements": {"rendered_pcm": {"applied_gain_db": 0.0}},
            "non_publishing": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = root / "candidates" / logical_path / generated_path
            candidate_path.parent.mkdir(parents=True)
            candidate_path.write_bytes(b"canonical candidate")
            bundled = {
                "candidate_path": candidate_path.relative_to(root).as_posix(),
                "candidate_evidence": copy.deepcopy(evidence),
            }
            def fake_write(
                _asset: dict[str, object], output: Path,
                _toolchain: dict[str, object], _versions: dict[str, str],
            ) -> dict[str, object]:
                reproduced = output / generated_path
                reproduced.parent.mkdir(parents=True)
                reproduced.write_bytes(b"canonical candidate")
                return copy.deepcopy(evidence)
            patches = (
                mock.patch.object(sound_release, "checked_toolchain", return_value={}),
                mock.patch.object(sound_release, "verify_toolchain", return_value={"opusenc": "fixture"}),
                mock.patch.object(sound_release, "write_review_candidate", side_effect=fake_write),
            )
            with patches[0], patches[1], patches[2]:
                sound_release.verify_review_bundle_candidates(
                    root, {logical_path: bundled}, {logical_path: {}},
                )
                candidate_path.write_bytes(b"forged candidate")
                forged = copy.deepcopy(evidence)
                forged["output_sha256"] = hashlib.sha256(b"forged candidate").hexdigest()
                bundled["candidate_evidence"] = forged
                with self.assertRaisesRegex(sound_release.ReleaseError, "deterministic current output"):
                    sound_release.verify_review_bundle_candidates(
                        root, {logical_path: bundled}, {logical_path: {}},
                    )


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
