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
at least a patch release. Each release publishes a deterministic
`atrinik-sound-VERSION.tar.gz` archive and `SHA256SUMS`; consumers pin the tag,
source commit, asset URL, and SHA-256 digest.
