# Edwin “Mamoru” Miltenburg background review

Retrieved and reviewed on 2026-08-10 for Atrinik sound issue #18. This evidence
applies only to the ten exact MIDI source hashes below.

## First-party authorship and grant

Edwin Miltenburg committed the authoritative identity and grant directly to
`atrinik/classic`:

- commit `b7efddeec32e6866cf5d0387044c7536f6d0f78b`, authored by Edwin
  Miltenburg, says `new bgmusic: burnt_forest2.mid by me, update LICENSE` and
  places all ten filenames under `Edwin "Kiana" Miltenburg - GPLv2`;
- commit `9678f7469fafd90215a4c36ce30a7d7a59bb8cf1`, also authored by Edwin,
  changes that group to his legal name while retaining all ten filenames;
- commit `2b2db15193b51ca6549d6fed32c4cb04d1370ae7`, again authored by Edwin,
  corrects the nickname to `Mamoru` while retaining the same group and grant.

The corresponding immutable `media/LICENSE` Git blobs are respectively
`c313da2c6b315996c75f1acf68f4fbfd2e7561b4`,
`e6e83ae25f20321f1d9c1ffbf0b080ce4ff29356`, and
`e5c53ad427d27393267405c8b2db6f07d3fac9a1`. Each reviewed tree contains the
complete GNU GPL Version 2, June 1991 text as root `License` Git blob
`d8cf7d463e2a4f064a157fa994bb394d3623b9cc`; no later-version option is stated. The exact commit objects and
full blobs are retrievable from <https://github.com/atrinik/classic>.

## Exact source identity

The ten current files are unchanged from `atrinik/sound` commit
`c2b8af8426b6275b345fa906348db51ca16336f5`, which co-committed the source
bytes and the `Edwin "Mamoru" Miltenburg - GPLv2` notice.

| Logical path | Source SHA-256 | Git blob |
| --- | --- | --- |
| `background/banrril.mid` | `85309d31655ecd4b26bcc1f4652a25ef5408eb614121ede7296c4576a39fd24c` | `b597a5b7af04130823e295ee6a868b6d9ae9e102` |
| `background/burnt_forest.mid` | `6dff5a5b2e3f92c7b765b73e4d2636072c366b1499f1201de1496b204c66930b` | `adb8c601c7687cf0fa7c1e44606335280cba7983` |
| `background/burnt_forest2.mid` | `8281a472059546ecb12784621ef1382f81a840e63bc632cd820337955013e14d` | `7b8d4755bff4b4455f777d09686dc1272bc5df22` |
| `background/chether.mid` | `e9a4014dfec6513ff084cfd2fe3848afb84d040b28caa7606019a852262b7d8d` | `8eab2e064346527a0f6de60d4ab8e4a75132684a` |
| `background/denkash.mid` | `6199a44746ca77bbb6a649e0a6b1c6063ba4ce8e38144c0b562c9119ca630569` | `88d5d6b00bdb6a824ed0debed7f855c17a98911d` |
| `background/denkash-finale.mid` | `8a80b92a47976578a5d39936e0d359c4f1ef3306b5526c4ee7c08f8002c2e2f1` | `6b3df69839856323b93dc38ed0f32a0ce3138259` |
| `background/endurance.mid` | `814ac9be92ff3dc7fe1fa584e402ac365abfab32d4a167c21cca2e99c9fbdbe0` | `4413236571905f1f4946525c354033b26443e3ab` |
| `background/essilda-finale.mid` | `bd7da944dbb9cdd8ff54978e82032a503d89e2d899968966a7b602f0afcf2dc3` | `c4c019cec32afd50e1f93373c8097ea8741b5aff` |
| `background/kaitindam.mid` | `e91ad620e03a9919e34b0e149d3ca118032f11fe5f8eb490246ddeb2ad0165e0` | `7d928378f918d644d0939ee0a91acde51be45755` |
| `background/tutorialisland.mid` | `401cbadc54a00dc903775d5faa4fe7c81423e9711a8ca86754287b19ae913f25` | `c3dfd7babd4ac904e78955ccf292a4169d21ea54` |

The short Git blob identifiers above are recorded for human cross-checking;
the full source SHA-256 values and immutable sound commit bind the exact bytes.
Embedded metadata independently names Edwin on both Burnt Forest files,
`chether.mid`, and `endurance.mid`. Both Burnt Forest files supply the title
`Burnt Forest`; no placeholder copyright in another file is treated as real.

## Decision

All ten exact inputs are approved under `GPL-2.0-only` for deterministic
conversion to Opus and redistribution with the corresponding source. The
runtime archive packages the complete GPLv2 text, exact author and source
coordinate, and a dated Atrinik MIDI-to-Opus modification notice. The source
release retains every authored MIDI at its logical path. Any source, notice,
license, author, or evidence change requires a new review.
