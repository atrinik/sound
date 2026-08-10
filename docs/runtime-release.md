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

The current inventory intentionally records fail-closed findings for ambiguous
`Permission to use`, `Freeware`, noncommercial, incomplete, and missing notices.
Those sources are not silently omitted: while any finding remains, releases
publish the complete blocker report and no runtime archive. Source archives
continue unchanged. Remediation requires documentary provenance and permission;
editing a status without changing its underlying notice is rejected when the
manifest is regenerated.

## Toolchain and encoding profile

`manifests/audio-toolchain.json` pins the Linux build image by digest and source
commit, direct package versions, upstream archive checksums, renderer settings,
FreePats instrument bank and exception, Opus encoder, independent decoder, and
the SDL3_mixer full-decode probe delivered by `atrinik/devcontainer#21`.
`tools/audio/Dockerfile` creates the exact runnable environment.

The release recipe renders signed 16-bit PCM at 48 kHz, explicitly disables
the tracker's otherwise-random dither, and encodes stereo music at
160 kb/s VBR with `--music --comp 10`, and channel-scales mono to 80 kb/s. Ogg
serial numbers derive from the immutable source SHA-256, all input comments are
discarded, and archive timestamps/ownership/order are fixed. Vorbis inputs are
explicitly labeled as second lossy generations and remain subject to the
quality gate; converting them to FLAC would not restore lost information.

No input is truncated: each renderer runs to decoder EOF. Background entries
are loopable and effects are one-shot. A generated output must pass `opusinfo`,
fully decode through FFmpeg and the pinned SDL3_mixer Opus backend, contain
nonzero PCM, remain within the documented 2.5-second duration tolerance, and
report no clipping. The runtime manifest reports source/runtime totals so
bitrate or size changes are reviewable.

If a renderer reaches full scale, the pipeline deterministically attenuates
that PCM to a -2 dBFS peak before encoding and records the original peak,
clipping flag, and applied gain. It rejects clipping after this transform and
again after Opus decoding.

## Local validation

The metadata and packaging checks need only Python 3.11+, Bash, and Git:

```sh
tools/validate.sh
python3 tools/sound_release.py blockers
```

Build the pinned conversion environment and the six-format fixture archive:

```sh
docker build --file tools/audio/Dockerfile --tag atrinik-sound-audio .
mkdir -p build/fixture-a build/fixture-b
docker run --rm \
  --volume "$PWD:/workspaces/sound:ro" \
  --volume "$PWD/build/fixture-a:/output" \
  --env SOURCE_DATE_EPOCH=1700000000 \
  atrinik-sound-audio \
  python3 tools/sound_release.py build-runtime v0.0.0 /output --fixtures
docker run --rm \
  --volume "$PWD:/workspaces/sound:ro" \
  --volume "$PWD/build/fixture-b:/output" \
  --env SOURCE_DATE_EPOCH=1700000000 \
  atrinik-sound-audio \
  python3 tools/sound_release.py build-runtime v0.0.0 /output --fixtures
cmp build/fixture-a/atrinik-sound-fixture-0.0.0.tar.gz \
  build/fixture-b/atrinik-sound-fixture-0.0.0.tar.gz
```

The fixture plan covers MIDI, MOD, S3M, XM, Vorbis music, an effect,
mono/stereo, loop, seek, stop, and short-effect cases. The asset pipeline proves
decode and media invariants. `atrinik/classic#44` owns matching interactive
SDL3_mixer playback assertions for loop, seek, and stop; the exact generated
paths in `manifests/fixture-plan.json` are the boundary between the repositories.

After all blockers have documentary remediation, a full build is:

```sh
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct 'vX.Y.Z^{commit}')"
docker run --rm \
  --volume "$PWD:/workspaces/sound:ro" \
  --volume "$PWD/build/release:/output" \
  --env SOURCE_DATE_EPOCH \
  atrinik-sound-audio \
  python3 tools/sound_release.py build-runtime vX.Y.Z /output
python3 tools/sound_release.py checksums build/release
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
licenses/background-LICENSE
licenses/effects-LICENSE
manifest.json
```

Consumers verify the release asset against `SHA256SUMS`, then verify every
payload against `manifest.json`. Requests use `logical_path` as the lookup key
and load `generated_path`; raw MIDI or tracker files are never staged into a
runtime bundle. Tags or URLs alone are insufficient pins.

Workspace profile selection/staging belongs to `atrinik/atrinik#267`. Classic
client fallback, decoder enforcement, playback behavior, and package tests
belong to `atrinik/classic#44`. Replacement client integration is not yet
available; boundaries `atrinik/atrinik#266`, `#269`, and `#270` still delimit
replacement build, scenario, and runtime integration. This repository therefore
uses owner-native validation rather than substituting the Classic stack.
