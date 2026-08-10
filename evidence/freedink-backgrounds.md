# FreeDink background review

Retrieved and reviewed on 2026-08-10 for Atrinik sound issue #18. This
evidence applies only to the four byte-identical source hashes listed below.

## Immutable official release

GNU publishes the official FreeDink data release at:

- release: <https://ftp.gnu.org/gnu/freedink/freedink-data-1.08.20190120.tar.gz>
- archive size: `71473728` bytes
- archive SHA-256: `715f44773b05b73a9ec9b62b0e152f3f281be1a1512fbaaa386176da94cffb9d`

The archive's `README.txt` has SHA-256
`481981942594fff8a9373610c09c417b889482c1c7b1a242dd5abf27f97c52ba`.
It states that the preserved original Dink Smallwood data-pack license covers
all files in its explicit inventory. That inventory includes
`Sound/insper.mid`, `Sound/lively.mid`, and `Sound/love.mid`. The reproduced
grant is the standard Zlib license and permits use, alteration, and
redistribution subject to its notice conditions.

The archive's `README-REPLACEMENTS.txt` has SHA-256
`0ccc8f5fee7ed8a76daa6ffb81a3668c072d7934d34f7bf8b2b09430b365ed5e`.
For replacement `105.mid`, it records copyright (C) 2008 Sylvain Beucler and
offers `GPLv3+ | Art Libre | CC-BY-SA`. This review selects
`GPL-3.0-or-later`; the archive's complete GPL version 3 text has SHA-256
`8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903`.

## Exact source identity

| Logical path | Atrinik and release-member SHA-256 | Release member | License |
| --- | --- | --- | --- |
| `background/insper.mid` | `65aec6f7f05615422bd7da2301b07a6bc688c1fb219b43b7571b4b68d37cf7ea` | `dink/Sound/insper.mid` | `Zlib` |
| `background/lively.mid` | `8fc6aae4b07fe0d03eabe100708f8582e0af5f2eab436c91833f5ea813b836dd` | `dink/Sound/lively.mid` | `Zlib` |
| `background/love.mid` | `b5aa92dfe42a2da9820e5ccea05cd1c5b64b5a71e1f71afaab24ae0542d65db0` | `dink/Sound/love.mid` | `Zlib` |
| `background/piano.mid` | `0c464dd925d59415fdad806f55682e2bcc8434c5be81fa783c69a6d7d6bf0b53` | `dink/Sound/105.mid` | `GPL-3.0-or-later` |

Each Atrinik input is byte-identical to the named member of the hash-pinned
official archive. The corrected authored notice preserves the original-data
grant separately from Sylvain Beucler's replacement grant. The runtime archive
retains that notice and the selected complete license text.

## Decision

The four exact inputs above are approved for deterministic conversion to Opus
and redistribution under their recorded SPDX expressions. Any byte, notice,
logical-path, or upstream-evidence change requires a new review.
