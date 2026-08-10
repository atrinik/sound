# Deterministic Opus runtime release

## Contract and current gate

The repository preserves 339 canonical mixed-format sources (32,026,363 bytes):
126 MIDI, five MOD, five S3M, seven XM, and 196 Ogg Vorbis files. The generated
runtime product normalizes every deliverable source to Opus in its standard Ogg
encapsulation without changing any authored file or content-side filename.

`manifests/source-assets.json` is the source-of-truth inventory. Each entry has
a stable ID, legacy logical/source path, collision-free generated path, source
hash and media metadata, renderer/encoder recipe, loop and tail policy,
transformation note, and exact notice reference. Runtime generation adds the
output hash, size, codec/container, sample rate, channels, duration, peak,
loudness, clipping result, and rendered-PCM measurements.

The current inventory records 307 fail-closed license/provenance
findings. This includes terse GPL/CC headings until a per-asset review binds
the source and notice hashes, SPDX interpretation, reviewer, timestamp, and a
Git-tracked, non-symlink, content-hash-verified evidence document under
`evidence/`; ambiguous `Permission to use`,
`Freeware`, Sampling Plus, noncommercial, incomplete, and missing notices have
no candidate interpretation. Approval is never a default-allow keyword filter.
All 196 preserved Vorbis inputs also have source-hash-bound quality reviews
pending, producing 503 total gates. They are not silently omitted: while any
finding remains, releases
publish the complete blocker report and no runtime archive. Source archives
continue unchanged.

`manifests/vorbis-quality-reviews.json` is the independent review ledger. A
passed entry binds the source, toolchain, reviewed evidence artifact, and exact
generated output hashes, plus a GitHub reviewer identity and canonical UTC
timestamp. The referenced `evidence/` file must be tracked and match its hash;
stale, malformed, missing, or failed evidence blocks publication.
`manifests/license-reviews.json` records those evidence-backed per-asset
decisions, so an asset replacement cannot inherit a notice-level approval.
These manifests and the
stable sound IDs are shared groundwork for `atrinik/sound#13`, not a parallel
Classic-only contract.

Versioned JSON Schemas under `schemas/` are the consumer contract for source,
toolchain, fixture, review, and generated runtime manifests. Producers reject
missing and unknown fields; each runtime archive carries its runtime schema.

## Toolchain and encoding profile

`manifests/audio-toolchain.json` pins the Linux build image by digest and source
commit, an immutable Ubuntu package snapshot, direct package versions, upstream archive checksums, renderer settings,
FreePats instrument bank and exception, Opus encoder, independent decoder, key
runtime-library and executable hashes, exact asset license texts, and the
repository-owned SDL3_mixer full-decode/playback probe compiled against the
libraries delivered by `atrinik/devcontainer#21`.
`tools/audio/Dockerfile` creates the exact runnable environment.

The checked quality budget authoritatively generates and validates the release
recipe. It renders signed 16-bit PCM at 48 kHz, explicitly disables
the tracker's otherwise-random dither, and encodes stereo music at
160 kb/s VBR with `--music --comp 10`, and channel-scales mono to 80 kb/s. Ogg
serial numbers derive from the immutable source SHA-256, all input comments are
discarded, and archive timestamps/ownership/order are fixed. Vorbis inputs are
explicitly labeled as second lossy generations and remain subject to the
quality gate; converting them to FLAC would not restore lost information.

No input is truncated: each renderer runs to decoder EOF. Background entries
are loopable and effects are one-shot. A generated output must pass `opusinfo`,
fully decode through FFmpeg and the pinned SDL3_mixer Opus backend, contain
nonzero PCM, match the expected decoded length, remain within the documented
2.5-second duration tolerance, and report no clipping. Fixture tracks also
execute device-free seek, stop, loop, decoded-channel, and short-effect
natural-EOF transitions through SDL3_mixer. The
runtime manifest reports source/runtime totals so bitrate or size changes are
reviewable.

If a renderer's peak exceeds -2 dBFS, the pipeline deterministically attenuates
that PCM to the target before encoding and records the original peak, whether
the input actually clipped, and the applied gain. It rejects clipping after
this transform and again after Opus decoding.

## Local validation

The metadata and packaging checks need only Python 3.11+, Bash, and Git:

```sh
tools/validate.sh
python3 tools/sound_release.py blockers
```

Tracker duration refresh is performed inside the pinned image, never copied
from the source manifest:

```sh
docker run --rm --volume "$PWD:/workspaces/sound:ro" atrinik-sound-audio \
  python3 tools/sound_release.py measure-trackers
```

After a per-asset license review passes, generate a non-publishing candidate
for critical listening and its exact output/toolchain evidence without waiting
for the quality ledger to pass:

```sh
docker run --rm --volume "$PWD:/workspaces/sound:ro" \
  --volume "$PWD/build/review-candidate:/output" atrinik-sound-audio \
  python3 tools/sound_release.py build-review-candidate effects/example.ogg /output
```

Build the pinned conversion environment and the six-format fixture archive:

```sh
docker build --file tools/audio/Dockerfile --tag atrinik-sound-audio .
mkdir -p build/fixture-a build/fixture-b
export ATRINIK_SOURCE_COMMIT="$(git rev-parse HEAD)"
export ATRINIK_SOURCE_TREE="$(git rev-parse 'HEAD^{tree}')"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspaces/sound:ro" \
  --volume "$PWD/build/fixture-a:/output" \
  --env SOURCE_DATE_EPOCH=1700000000 \
  --env ATRINIK_SOURCE_COMMIT \
  --env ATRINIK_SOURCE_TREE \
  atrinik-sound-audio \
  python3 tools/sound_release.py build-runtime v0.0.0 /output --fixtures
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspaces/sound:ro" \
  --volume "$PWD/build/fixture-b:/output" \
  --env SOURCE_DATE_EPOCH=1700000000 \
  --env ATRINIK_SOURCE_COMMIT \
  --env ATRINIK_SOURCE_TREE \
  atrinik-sound-audio \
  python3 tools/sound_release.py build-runtime v0.0.0 /output --fixtures
cmp build/fixture-a/atrinik-sound-fixture-0.0.0.tar.gz \
  build/fixture-b/atrinik-sound-fixture-0.0.0.tar.gz
```

The fixture plan covers MIDI, MOD, S3M, XM, Vorbis music, an effect,
mono/stereo, loop, seek, stop, and short-effect cases. The asset pipeline proves
decode, media, and device-free SDL3_mixer control invariants.
`atrinik/classic#44` owns matching interactive client playback assertions; the
exact generated paths in `manifests/fixture-plan.json` are the boundary between
the repositories.

After all blockers have documentary remediation, use the guarded publisher for
a full build. It fails if Git status cannot be obtained, rejects any tracked or
untracked worktree change, validates tracking and evidence on the host, binds
the tag/commit/tree, and only then attests those checks to the isolated audio
container. This wrapper is the supported full-build entry point:

```sh
tools/build-release-assets.sh X.Y.Z
(cd build/release && sha256sum --check SHA256SUMS)
```

Run it twice from clean checkouts of the same commit and compare the archives,
runtime manifests, and checksum files byte for byte. GitHub Actions performs
the equivalent fixture proof on every pull request.

## Runtime archive layout and consumption

For version `X.Y.Z`, the archive root is
`atrinik-sound-runtime-X.Y.Z/` and contains:

```text
audio/background/<legacy-name-and-extension>.opus
audio/effects/<legacy-name-and-extension>.opus
licenses/audio-toolchain.json
licenses/CC-BY-3.0.txt
licenses/CC-BY-SA-3.0.txt
licenses/CC-BY-SA-3.0-DE.txt
licenses/CC0-1.0.txt
licenses/GPL-2.0.txt
licenses/GPL-3.0.txt
background/LICENSE
effects/LICENSE
schemas/runtime-manifest-v1.schema.json
schemas/audio-toolchain-v1.schema.json
manifest.json
SHA256SUMS
```

Consumers verify the release asset against the release-level `SHA256SUMS`, then
verify every unpacked file against the archive's own `SHA256SUMS` and every
payload against `manifest.json`. Requests use `logical_path` as the lookup key
and load `generated_path`; raw MIDI or tracker files are never staged into a
runtime bundle. In addition to JSON Schema validation, consumers reject
duplicate logical/generated paths, unsafe paths, missing checksum members, and
payload hashes that disagree with the manifest. Tags or URLs alone are
insufficient pins.

Workspace profile selection/staging belongs to `atrinik/atrinik#267`. Classic
client fallback, decoder enforcement, playback behavior, and package tests
belong to `atrinik/classic#44`. Replacement client integration is not yet
available; boundaries `atrinik/atrinik#266`, `#269`, and `#270` still delimit
replacement build, scenario, and runtime integration. This repository therefore
uses owner-native validation rather than substituting the Classic stack.
