# KQ GPL-2.0 background review

Retrieved and reviewed on 2026-08-10 for Atrinik sound issue #18. This
evidence applies only to the nine byte-identical source hashes listed below.

## Authoritative release and grant

The official KQ SourceForge project identifies the project license as GNU GPL
version 2 and publishes `kq-0.99.tar.gz` as its latest source release:

- project: <https://sourceforge.net/projects/kqlives/>
- files: <https://sourceforge.net/projects/kqlives/files/>
- download: <https://sourceforge.net/projects/kqlives/files/latest/download>
- downloaded archive SHA-256: `a8742d0a8781bd3626aef17ae382525b0abb4ab194004c9acf9f136b7be2b6fd`

The source archive contains the complete GPL version 2 text at
`kq-0.99/COPYING` (SHA-256
`231f7edcc7352d7734a96eef0b8030f77982678c516876fcb81e25b32d68564c`).
Its README describes KQ as the complete open-source RPG accompanied by music
and sound effects and identifies `music/` as the music files used by KQ. The
release contains no separate music exception or more restrictive music notice.

## Exact source identity

| Logical path | Atrinik and release-member SHA-256 | Release member |
| --- | --- | --- |
| `background/aa_arofl.xm` | `1830756c232f101a43e4a302e228c671bfef0bb62fa2ef262eaec1e050fbb0e4` | `music/aa_arofl.xm` |
| `background/comeback.mod` | `cce0f3f5e50610ad92d4204d25a8e3fb3cf219201ecf14b233af6d76e1c72a91` | `music/comeback.mod` |
| `background/enfero.xm` | `ee6d228cf70a47d5c6665e72ebb69baa0902a33c7b29e02f0bd45043a87bfff5` | `music/enfero.xm` |
| `background/eranasp.mod` | `04351f60469d941a664a727d112d9e0393e767c2105905e15c113fb9f2c942f0` | `music/eranasp.mod` |
| `background/infanita.mod` | `0eabaa89c222a0f26920f5f1ee6bb284deb6ec4444d0fedb8e9d794c7f4a8016` | `music/infanita.mod` |
| `background/rain.s3m` | `1d384070d989a8739799d7d3e689619edbe9834a2e1523a478db72eccd4116d2` | `music/rain.s3m` |
| `background/rend.s3m` | `8ed26cc474e6ba30ad2774fa19eb4828e7f3aa190eac2385ea0ff740602c38e9` | `music/rend5.s3m` |
| `background/town.mod` | `4484aff95c4b7158e7bdcdc75e4e1d66fad5b0b0c71e11f8e23da2571233e060` | `music/town.mod` |
| `background/walk.s3m` | `8de75898a0fa27bf8627208d0fd59756793b3b20f7abb4ad437423e04d885f9f` | `music/walk.s3m` |

Each Atrinik source is byte-identical to the named official release member.
GPL-2.0 permits conversion and redistribution under its conditions; the
complete license text and attribution are retained in the runtime archive.

`background/waterworld.xm` is intentionally excluded because it is not present
in the official `kq-0.99` release. The shared notice is not broadened to that
asset.

## Decision

The nine exact Atrinik inputs above are approved under `GPL-2.0-only` for
conversion to Opus and redistribution in the complete sound archive. Any byte
change, notice change, or different logical path requires a new review.
