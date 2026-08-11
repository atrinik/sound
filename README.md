# Atrinik sound assets

This repository owns the background music and sound effects distributed with
Atrinik clients. The maintained consumer is
[`atrinik/classic/client`](https://github.com/atrinik/classic/tree/main/client);
the fresh [`atrinik/client`](https://github.com/atrinik/client) will consume a
released archive when replacement integration lands. Consumers use immutable
checksum-pinned releases instead of Git submodules.

## Licensing and attribution

These assets do not have one blanket repository license. The `LICENSE` and
`README.md` files under `background/` and `effects/` identify the terms and
attribution for their respective assets. Preserve those files and update the
nearest applicable attribution when adding or replacing media.

## Releases

Every squash merge uses its Conventional Commits pull-request title to create
at least a patch release. Each release continues to publish the preserved-source
`atrinik-sound-VERSION.tar.gz` archive and `SHA256SUMS`.

The checked [source manifest](manifests/source-assets.json) inventories all 339
current audio inputs and maps each legacy logical path to a collision-free Opus
path. For example, `background/fireside.mid` maps to
`audio/background/fireside.mid.opus`; consumers resolve the mapping instead of
renaming authored content.

When every source has exact conversion and redistribution permission and every
second-generation conversion has source-hash-bound quality approval, the same
release also publishes `atrinik-sound-runtime-VERSION.tar.gz`. The runtime
archive contains only generated `.opus` audio, its complete measured manifest,
the applicable notices, and the pinned transformation contract. A release with
any unresolved finding publishes an explicit
`atrinik-sound-runtime-VERSION-BLOCKED.json` report and no partial runtime
archive.

Approvals are immutable-input contracts: license reviews bind source, notice,
and SPDX hashes, while Vorbis quality reviews additionally bind the exact
toolchain, evidence artifact, and generated output. Versioned JSON Schemas in
[`schemas/`](schemas/) define the checked and packaged manifest interfaces.

Consumers pin source and runtime products independently by all four immutable
coordinates:

1. release tag, such as `v1.2.0`;
2. the tag's source commit;
3. the exact GitHub release asset URL;
4. the asset's entry in `SHA256SUMS`.

See [the runtime release contract](docs/runtime-release.md) for build,
determinism, quality, validation, and consumer details.

## Local Classic playtest tree

Source-building Classic playtesters can opt into a complete, local-only tree
without weakening the released-runtime gates:

```sh
python3 tools/sound_release.py build-playtest-tree build/classic-playtest
python3 tools/sound_release.py verify-playtest-tree build/classic-playtest
```

The command requires a clean Git checkout and the separate pinned playtest
audio toolchain; released-runtime inputs remain unchanged. It
copies all 196 Vorbis inputs byte-for-byte, deterministically renders the 143
MIDI/tracker inputs to Opus, and stages every payload at its existing legacy
logical path. The canonical manifest records the source and actual payload
codecs, so content-based SDL3_mixer decoding is required where a legacy
extension names the authored format.

The resulting directory remains below ignored `build/` state. Its marker and
manifest declare `playtest_only: true` and `publishable: false`; it is not an
archive, release input, cache, package, container layer, or provenance or
listening approval. An existing verified tree is reused, while an invalid,
stale, dirty, or concurrently changing input fails without replacing it.
