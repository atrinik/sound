# OpenMSX GPL-2.0 background review

Retrieved and reviewed on 2026-08-10 for Atrinik sound issue #18. This
evidence applies only to the two byte-identical source hashes listed below.

## Authoritative source and grant

The official `OpenTTD/OpenMSX` repository at commit
`312ca0ae46a271fb65ba49674b5e935ca0f41036` states in `README.md` that the
OpenMSX music set is copyrighted by the OpenMSX authors and licensed under GNU
GPL version 2. Its `src/themes.list` identifies Tistou Blomberg as the musician
and records the supplied titles for both reviewed tracks. The same tree
contains the complete GPL version 2 text in `LICENSE`.

Immutable repository coordinates:

- repository: <https://github.com/OpenTTD/OpenMSX>
- reviewed commit: <https://github.com/OpenTTD/OpenMSX/commit/312ca0ae46a271fb65ba49674b5e935ca0f41036>
- `README.md` Git blob: `55cc1b40292edfb7f6d902e66b9af05c3c2fa9fc`
- `src/themes.list` Git blob: `e80313839c5fa614dbee544d7bd90181c14a3cdc`
- `LICENSE` Git blob: `d159169d1050894d3ea3b98e1c965c4058208fe1`

## Exact source identity

| Logical path | Atrinik SHA-256 | Official path | Official Git blob |
| --- | --- | --- | --- |
| `background/run_for_your_life.mid` | `654f402855dd82d00a7b6ec596fa0aeb8906431224e79a57f115db8c2fb9a4d0` | `src/run_for_your_life.mid` | `482db571905e1e44ab037657f1a7f8d36c003594` |
| `background/ultimate_run.mid` | `b1b8745f04e3f16e4924d6b1b9a489ead889001343fde3ed947fda2921199ded` | `src/ultimate_run.mid` | `c7b05b1add33c2a93c52ccdca9a0b8034c93b57a` |

For each row, `git hash-object` of the Atrinik file equals the official Git
blob identifier. The reviewed bytes are therefore the complete files covered
by the repository's GPL-2.0 grant. GPL-2.0 permits conversion and
redistribution under its conditions; the complete license text and attribution
are retained in the runtime archive.

`background/the_fast_route.mid` is intentionally excluded. Its Atrinik Git
blob `fdde1fc537d461dca1bc3333e5bfa498483e3a5b` does not match either official
revision (`44901e4dd2fba35365f3f61f39f9b7af0865337b` at its introduction or
`dd7488a822ec2983daded17a9d1761892d9fc77f` after the only recorded edit), so
the shared notice is not broadened to that asset.

## Decision

The two exact Atrinik inputs above are approved under `GPL-2.0-only` for
conversion to Opus and redistribution in the complete sound archive. The
packaged per-asset notices preserve Tistou Blomberg, each supplied title, the
OpenMSX copyright, immutable source coordinate, and Atrinik's dated MIDI-to-Opus
modification statement. Any byte, notice, or different logical path requires a
new review.
