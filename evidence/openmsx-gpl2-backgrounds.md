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

`background/the_fast_route.mid` is a modified derivative rather than a
byte-identical copy. OpenMSX introduced it at commit
`4e4109111f5c7c707dd1a7c78c098850be8575a1` (Git blob
`44901e4dd2fba35365f3f61f39f9b7af0865337b`) and made its only upstream edit at
commit `1bc84b0f821daef86f2e938b75619a3085f79dd9` (Git blob
`dd7488a822ec2983daded17a9d1761892d9fc77f`). `src/themes.list` identifies
musician `mimm` and supplied title `The Fast Route`.

The Atrinik source SHA-256
`f66dcda2d8916961c85f8468ad8e428e92f6a9fd5ab7bb3d32acc3a273d9e9ce`
is a Rosegarden rewrite of the edited official revision. After normalizing the
96-to-480 PPQN timebase and note-off velocity, all 7,030 local note events
exactly equal the upstream events outside channel 5. The rewrite omits upstream
channel 5 (312 note events and four setup events), adds 20 controller defaults,
a channel-10 program event, Rosegarden boilerplate, and a 12/8 time signature,
and retains the exact tempo. This complete event comparison establishes the
modified-work identity permitted by GPL-2.0.

## Decision

The three Atrinik inputs above are approved under `GPL-2.0-only` for
conversion to Opus and redistribution in the complete sound archive. The
packaged per-asset notices preserve Tistou Blomberg, each supplied title, the
`mimm` credit and Fast Route rewrite details where applicable, the OpenMSX
copyright, immutable source coordinates, and Atrinik's dated MIDI-to-Opus
modification statement. Any byte, notice, or different logical path requires a
new review.
