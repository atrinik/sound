# OpenGameArt Brandon Morris background review

Retrieved and reviewed on 2026-08-10 for Atrinik sound issue #18. This
evidence applies only to the four source hashes listed below.

## Authoritative grants and authorship

OpenGameArt identifies each publication as music by Brandon Morris (also
published as HaelDB or Augmentality) and currently offers the complete work
under CC0, alongside the site's OGA-BY alternative:

| Atrinik logical path | OpenGameArt publication | Published file | Published-file SHA-256 |
| --- | --- | --- | --- |
| `background/evil_temple.ogg` | <https://opengameart.org/content/evil-temple-ambiance-loop> | <https://opengameart.org/sites/default/files/evil_temple.ogg> | `d2449bcd9c560145d25ba4437892b947e16e371c08441164618e0a0ed676a5dc` |
| `background/lost_in_meadows.ogg` | <https://opengameart.org/content/lost-in-the-meadows> | <https://opengameart.org/sites/default/files/lost%20in%20the%20meadows_0.flac> | `1b11acb81dc34b0cfa73739c268fcf8ef14f425319ac288f741d4541455846aa` |
| `background/running.ogg` | <https://opengameart.org/content/running-from-something> | <https://opengameart.org/sites/default/files/running%20from%20something.ogg> | `9ab769a9172ebbe4cf84c455c8b45614d1d64c836986b1804aca8a6aaf5358c7` |
| `background/sewer_rats.ogg` | <https://opengameart.org/content/rat-sewer> | <https://opengameart.org/sites/default/files/ratsrats_0.ogg> | `0149b557a94140aefa0bf5c21b733eff7439e044138e14377faceec8d9627bb5` |

The Evil Temple publication additionally records the creator's statement that
the vocals are his own. No third-party vocal source is asserted by this
decision.

The first-party publication responses retrieved on 2026-08-10 are preserved
byte-for-byte so the author, submitter, license, title, and published-file
claims remain independently hash-verifiable:

| Publication | Capture | Capture SHA-256 |
| --- | --- | --- |
| Evil Temple Ambiance Loop | `evidence/captures/opengameart-evil-temple-ambiance-loop.html` | `42b52e20c0c49b7732ae6453cff4e174126872204f86dcd8dd360ae446c3f051` |
| Lost in the Meadows | `evidence/captures/opengameart-lost-in-the-meadows.html` | `4a1d8a3d9a1757845a3078f03ef9ee9975df63f368970e52ff132cd6919d64d6` |
| Running from Something | `evidence/captures/opengameart-running-from-something.html` | `99ec05b389340187aa785674190f8c7d34ddac8c2b769ab85f7136dde952d274` |
| Rat Sewer | `evidence/captures/opengameart-rat-sewer.html` | `ad41b1b5aa01ae8a83daa1ae4fdf8ff7915ab32dbbc06771c54ff40e1eca592b` |

CC0 1.0 permits copying, modification, conversion, and commercial
redistribution without an attribution condition. Atrinik nevertheless keeps
the creator and publication attribution in `background/LICENSE`.

## Exact Atrinik inputs

| Logical path | Atrinik source SHA-256 | Duration | Source/master comparison |
| --- | --- | ---: | --- |
| `background/evil_temple.ogg` | `c51d29768e038a96ad00ed656561f4f24ef75907ee9f258bd9095f64a17f2a01` | 84.000000 s | stereo 44.1 kHz; APSNR 169.524/169.538 dB |
| `background/lost_in_meadows.ogg` | `2f8184b6b3ac0c2d495ca5d37b2378c2e1f5ab2cc57dafb1631e2f15db8e1c43` | 108.068571 s | stereo 44.1 kHz; APSNR 165.612/165.587 dB |
| `background/running.ogg` | `7fe0de9e8d7af2b19e69c0f5f74c67bbf1296b91e1a6b2266f2e25acc6be4fc0` | 123.250000 s | stereo 44.1 kHz; APSNR 170.060/169.543 dB |
| `background/sewer_rats.ogg` | `c58926e6295dddc7b676d6c5837445517bf10ac8461e63bd751b39ab13e7a742` | 61.107279 s | stereo 44.1 kHz; APSNR 168.668/168.695 dB |

The repository files are smaller historical Vorbis encodings rather than
byte-identical downloads. The pinned Atrinik audio image
`sha256:310cc2b46fda6ab07ebabb618ef20c44bea92ff27d09f04d1dfe2c42b3bd0f00`
and FFmpeg 8.0.1 `apsnr` filter compared each complete publication with the
corresponding repository input. Matching duration, channel layout, sample
rate, and the reported full-stream APSNR establish that each reviewed input is
an encoding of the identified publication. This identity finding does not
serve as the separate source-to-Opus critical-listening approval required by
issue #21.

## Decision

The preserved first-party responses establish the author and CC0 grant, and
the published audio comparisons establish complete-work identity for the four
exact local source hashes. All four inputs are approved under `CC0-1.0` for
conversion to Opus and redistribution. The packaged notices retain the
supplied author/title/source and Atrinik's dated conversion statement even
though CC0 does not require attribution. Any source, capture, notice, or
encoding-identity change requires a new review.
