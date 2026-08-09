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
- Validate that required license files are non-empty, all referenced assets are
  tracked regular files, release packaging is deterministic, and consumer locks
  change coherently when a release is consumed.
- Commits and pull-request titles use Conventional Commits. Every squash merge
  is released by semantic-release.
- Keep generated archives under `build/`, preserve unrelated work, and finish
  with `git diff --check`.
- Update this `AGENTS.md` in the same change when major rework alters asset
  ownership, layout, licensing, packaging, consumption, or validation.
