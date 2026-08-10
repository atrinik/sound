# Atrinik sound repository guide

- This repository owns separately released music and effects. The maintained
  consumer is `atrinik/classic/client`; replacement consumption belongs to
  `atrinik/client` when its integration lands. Keep playback and packaging code
  with the consuming client.
- There is no blanket repository license. Preserve the applicable `LICENSE`
  files, provenance, attribution, author, source URL, and modification notes for
  every asset. Do not add or replace audio without documented permission.
- Keep filenames portable and stable because runtime references are
  case-sensitive contracts. Update all consumers when a rename is unavoidable.
- Preserve the deterministic release archive layout and checksum publication.
  Consumers must use immutable checksum-pinned releases, not Git submodules.
- Keep mixed-format files as canonical authored sources. Runtime Opus is
  generated only under `build/`; never commit it or replace sources in place.
- Keep `manifests/source-assets.json`, `manifests/audio-toolchain.json`, the
  license and Vorbis quality-review ledgers, pinned tracker-duration ledger,
  versioned schemas, fixture plan,
  runtime builder, release workflow,
  and docs synchronized. Any
  ambiguous license, transformation permission, provenance, source hash,
  notice, or output closure must block the complete runtime archive; never ship
  a partial corpus.
- Validate that required license files are non-empty, all referenced assets are
  tracked regular files, release packaging is deterministic, and consumer locks
  change coherently when a release is consumed.
- Commits and pull-request titles use Conventional Commits. Every squash merge
  is released by semantic-release.
- Keep generated archives under `build/`, preserve unrelated work, and finish
  with `tools/validate.sh` and `git diff --check`.
- Update this `AGENTS.md` in the same change when major rework alters asset
  ownership, layout, licensing, packaging, consumption, or validation.
