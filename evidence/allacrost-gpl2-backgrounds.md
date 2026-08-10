# Hero of Allacrost background provenance research

Retrieved and reviewed on 2026-08-10 for Atrinik sound issue #18. This
evidence applies only to the six source hashes listed below.

## Authoritative release and grant

The official Hero of Allacrost SourceForge project published
`allacrost_demo_source_1.0.2.tar.gz` in its `allacrost-demo/1.0.2` release:

- download: <https://downloads.sourceforge.net/project/allacrost/allacrost-demo/1.0.2/allacrost_demo_source_1.0.2.tar.gz>
- archive SHA-256: `d679d2c216689084e5830b2a167f26afe53503ea84ef4bb6aaa5595e82c8f894`
- archive size: 63,823,397 bytes

The published SHA-256 and size are also recorded by the FreeBSD
`games/allacrost` port. The archive contains the complete GPL version 2 text as
`allacrost-1.0.2/COPYING`; its SHA-256 is
`32b1062f7da84967e7019d01ab805935caa7ab7321a7ced0e30ebe75e5df1670`.
The top-level README identifies the Allacrost Project copyright, grants
modification and redistribution under the GNU GPL, and explicitly lists
`mus/` among the included release directories. The release contains no
separate music exception or more restrictive music notice.

## Exact Atrinik inputs

| Logical path | Atrinik SHA-256 | Release member | Member SHA-256 | Full-stream APSNR (L/R) |
| --- | --- | --- | --- | --- |
| `background/betrayal_battle.ogg` | `8e647aa03114c76bd38181dd33028b5c33fda94e97ff576d03af70fa5516a038` | `mus/Betrayal_Battle.ogg` | `aae23f7ebdbdd9e5a2c85a0e083f6929fc87eeb61648506c46998868733e8b11` | 171.664/171.676 dB |
| `background/cave2.ogg` | `d3884b9f43b3eee290a678ead69496da3f02b9aced8ad4caf91ac36e8b294faf` | `mus/Cave2.ogg` | `a17273b928d1c271faed12a80246c7351a8dd87393bb157f91b29599f929e0c2` | 169.898/169.850 dB |
| `background/creature_awakens.ogg` | `015fb611c81ecd3a7dfd74f3a888287cdc898f19a0543bcdde239ab4bc2be251` | `mus/The_Creature_Awakens.ogg` | `ae5495a26fcfb5ab9c87050c58c2569977b3d338749f2ab236ce269ab2e01d6a` | 170.410/170.484 dB |
| `background/desert.ogg` | `b87a5289e9aa3005120e41513ad7a99bfd21b82dc28ed88fd9316359d2c8c464` | `mus/Desert.ogg` | `323386af88c5e96b4d3a52281b2d3ae403a8ce2c2631cf96583744dc43ac3e68` | 169.836/169.870 dB |
| `background/town_folk.ogg` | `0752297cca21295d30b1eb48820ea881b46bb9f5ed82d7ad3c8d78212d97e704` | `mus/Town_Folk.ogg` | `3d07662f04c6e6eab739a591d77858d09ad8bb3c664328bc35db5de12d8758b1` | 170.256/170.171 dB |
| `background/venturing_dragons.ogg` | `ea7aa1bedc36225e0027a10abb1e2fc21835059f9fb9969cfe0cc0d7de09e5b4` | `mus/Venturing_Dragons_in_the_Dark.ogg` | `f0bc5046c7e669440025145625f99f75a1a45b60456f10375546e6c95f141b67` | 169.592/169.699 dB |

The Atrinik files are smaller historical Vorbis encodings rather than
byte-identical release members. The pinned Atrinik audio image
`sha256:310cc2b46fda6ab07ebabb618ef20c44bea92ff27d09f04d1dfe2c42b3bd0f00`
and FFmpeg 8.0.1 `apsnr` filter compared each complete release member with its
repository input. Each pair also has identical duration, channel layout, and
sample rate. These checks establish that each reviewed input is an encoding of
the identified GPL-covered release member. They do not replace the separate
source-to-Opus critical-listening approval required by issue #21.

## Decision

The archive establishes source identity but not an affirmative music-specific
grant: its README licenses "code" under GPL-2.0 and separately asserts all
rights reserved. Merely including `mus/` in the source archive is insufficient
for the full-work permission required by issue #18. All six inputs remain
blocked pending authoritative music licensing or explicit permission.
