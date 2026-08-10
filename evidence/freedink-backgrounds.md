# FreeDink background review

Retrieved and reviewed on 2026-08-10 for Atrinik sound issue #18. This
evidence approves only the byte-identical replacement `piano.mid`. Three
original Dink Smallwood MIDIs remain blocked because the available upstream
statements conflict about their licensing scope.

## Immutable official release

GNU publishes the official FreeDink data release at:

- release: <https://ftp.gnu.org/gnu/freedink/freedink-data-1.08.20190120.tar.gz>
- archive size: `71473728` bytes
- archive SHA-256: `715f44773b05b73a9ec9b62b0e152f3f281be1a1512fbaaa386176da94cffb9d`

The archive's `README-REPLACEMENTS.txt` has SHA-256
`0ccc8f5fee7ed8a76daa6ffb81a3668c072d7934d34f7bf8b2b09430b365ed5e`.
For replacement `105.mid`, it records copyright (C) 2008 Sylvain Beucler and
the supplied work identity `“Rêverie” by Claude Debussy 1890`, and offers
`GPLv3+ | Art Libre | CC-BY-SA`. This review selects `GPL-3.0-or-later`; the
archive's complete GPL version 3 text has SHA-256
`8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903`.

The local `background/piano.mid` SHA-256 is
`0c464dd925d59415fdad806f55682e2bcc8434c5be81fa783c69a6d7d6bf0b53`,
exactly matching archive member `dink/Sound/105.mid`.

## Original MIDI conflict

The same archive's `README.txt` inventories `Sound/insper.mid`,
`Sound/lively.mid`, and `Sound/love.mid` beneath a reproduced original-data
Zlib notice. However, GNU's first-party sound-licensing page at
<https://www.gnu.org/software/freedink/doc/sounds/> says the 2008 Zlib
agreement excluded most WAV and MIDI files because many were not made by
RTsoft, and separately lists these three original MIDIs. The archive inventory
therefore does not prove that the rightsholder's Zlib authority covered their
music. Their byte identities are known, but their redistribution grants remain
ambiguous and fail closed.

## Decision

Only `background/piano.mid` is approved for deterministic conversion to Opus
and redistribution under `GPL-3.0-or-later`. Its packaged per-asset notice
preserves the supplied title/composer/date, Sylvain Beucler's exact copyright,
the release member identity, and Atrinik's dated MIDI-to-Opus modification
statement. `background/insper.mid`,
`background/lively.mid`, and `background/love.mid` remain blocked until an
explicit grant for their exact musical works is preserved. Any byte, notice,
logical-path, or upstream-evidence change requires a new review.
