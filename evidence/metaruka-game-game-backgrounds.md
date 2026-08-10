# Metaruka Game-Game background license review

Reviewed 2026-08-10 for the 17 Game-Game MIDI files under `background/`.

## Authoritative grant and publication

The preserved first-party response at
`evidence/captures/metaruka-game-game-20190826013953.html` was retrieved from
<https://web.archive.org/web/20190826013953id_/https://sites.google.com/site/metaruka/GameGame>.
It identifies Game-Game and Max McCracken, and grants CC BY-SA 3.0 Unported for
all files. Its SHA-256 is
`329b5abf485654b2e5c14674008000d50fab9fa92a53435643e0508eedc91c19`;
the Wayback CDX payload digest is `EPKBMXYDX34WUMVYDHHGFRPJ3NIXVCIL`.

The preserved original OpenGameArt submission at
`evidence/captures/opengameart-game-game-20100909174726.html` was retrieved
from
<https://web.archive.org/web/20100909174726id_/http://www.opengameart.org/content/game-game>.
It names artist Metaruka and submitter maxstack, specifies CC-BY-SA 3.0, and
links the exact original source archive. Its SHA-256 is
`7660f3f9d46671f0f18e167c7ef3e65876766ac3ecc300325e49123d0a0f8b70`;
the CDX payload digest is `SYRM7E5JYU4NHCJH3EGIZ3MQNLX5D3DJ`.

The still-retrievable first-party archive is
<https://opengameart.org/sites/default/files/game-game-music-sources.7z>.
It is 59,695 bytes with SHA-256
`4b0f8b05b24cf5f5421744dcddf5bf904c4335637f2e683b234f1cbc23091168`.
The authored OST at <https://archive.org/details/Game-gameOst> independently
corroborates the same 17 works; its ZIP SHA-256 is
`5ae5625ed08a20c10ff0d91cfd0fb8d347e1577dde6098b0290dbc7f052277e0`.

## Exact asset identity

Every local MIDI is byte-identical to its named member in the authoritative
source archive. The unchanged local bytes were introduced in Atrinik sound
commit `c2b8af8426b6275b345fa906348db51ca16336f5`.

| Local path | Source archive member | SHA-256 |
| --- | --- | --- |
| `background/gg.mid` | `00 Intro.mid` | `68b7a02ca76346b41e2e96dd0d8fb13116684fa403cb5fc6cf7006fdaf4bef0f` |
| `background/gg2.mid` | `01 Game-Game.mid` | `4abae7c0a9854a30761b07dad6276d003c2948fa70852ab4a6dd68b7e57891d4` |
| `background/lava_city.mid` | `02 Lava City.mid` | `aa25a3fe8b21ba2711203d00823487fd5ff46a669e4ae5c1478cfeec218cec49` |
| `background/ship.mid` | `03 Ship Interior.mid` | `6e7c3ed5d23d9a35b37b4b30a80d1636364a818e45c2dafa00591c5ef26e1864` |
| `background/underground.mid` | `04 Underground Cavern.mid` | `d8616799863f1c9776c6c868ab92fd970380afc86381ae340bfe37efec2b9cb6` |
| `background/tethanus.mid` | `05 Gaseous Tethanus.mid` | `8a862891c264c68c44a26b6e816ebe8c184729cd65c01648cf9beec94c2e86ba` |
| `background/pirates.mid` | `06 Pirates Attack.mid` | `b3efe980377b11be4e322f51138b13c6e7e4113c28d514d4dcd733fc65ee1837` |
| `background/high_mountains.mid` | `07 High In The Mountains.mid` | `060055cf7214d697c2634c2fac888f44135250789d8e6e4942b4d3d8b4a34103` |
| `background/endless_sands.mid` | `08 Endless Sands.mid` | `781b95d4316e1b984b7d83dff876444555b45d907b341d2198055d0ded17f636` |
| `background/green_forest.mid` | `09 Green Forest.mid` | `5104bee35e53b4d23ea86f6a035853166de6b670f5a2a5996a8e53495d3b7104` |
| `background/running_wild.mid` | `10 Running Wild.mid` | `938f539848e8fb35bd8884f8ab6e1eba88c1b2c1c3e6a26230537b18b7b352c7` |
| `background/vonstantine.mid` | `11 Die Vonstantine.mid` | `69a99efdc9e464376909f6b8f769d7932cf3a5ee5f620b0c075124e133aab305` |
| `background/battle.mid` | `12 Final Battle.mid` | `2d01d0017f138f84de360f54665ecaa7fa6258e9eab99cb2ca583df4b358e95c` |
| `background/the_end.mid` | `13 The End.mid` | `13480b76f02a55c22754d730632ff8553b55d564f18dbde5206ca39a2275d068` |
| `background/game_over.mid` | `1x Game Over.mid` | `77d49ab81085853fea1cb08cca78ccd9b8d11a961a196574c2a51c9d89834bcc` |
| `background/level_win.mid` | `1x Level Win.mid` | `89f4f1e663216e4b6d34b240403bfcffbf6b15d48202440c9fa9b765c0b486c8` |
| `background/interlude.mid` | `1x Short Interlude.mid` | `82f20d0347102873e359d0b7353cbc46cb8c6fa87fd6db1cd1fe53e01a39903b` |

## Decision

Approve all 17 files as `CC-BY-SA-3.0`. The first-party pages establish the
author, license, and exact source archive, and the byte comparisons bind every
local input to a granted archive member. Packaged notices preserve Max
McCracken (Metaruka/maxstack), the Game-Game work title, source and license
URLs, the supplied member title, and a dated Atrinik MIDI-to-Opus adaptation.
Each ledger record binds the source, evidence, SPDX expression, and exact
packaged heading-and-line bytes.
