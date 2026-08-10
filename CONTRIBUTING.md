# Contributing

Use a Conventional Commits pull-request title. Keep media attribution and the
nearest `LICENSE` and `README.md` files with every changed asset. Do not infer
or replace an asset license without documented provenance and permission.

After any audio or notice change, run `python3 tools/sound_release.py refresh`
and review the corresponding manifest entry. The refresh command fails closed
when tracker metadata cannot be carried forward from the exact unchanged source
hash. Run the aggregate `tools/validate.sh` before opening a pull request.

Encoding settings and tool versions are release contracts. Change
`manifests/audio-toolchain.json`, `tools/audio/Dockerfile`, tests, measured
quality evidence, and release documentation together; never update only the
command line or a mutable image tag.
