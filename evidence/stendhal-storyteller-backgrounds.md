# Stendhal Storyteller background research

Retrieved and reviewed on 2026-08-10 for Atrinik sound issues #18 and #20.
This evidence establishes six current, byte-identical repository blobs and
their Storyteller authorship, but does not approve them. All fourteen Atrinik
files under the shared Stendhal notice remain blocked.

## Immutable repository evidence

Authoritative repository: <https://github.com/arianne/stendhal> at commit
`fcd8330db06034098f9b164aa67fed82f261ae59`.

- `doc/sources/audio-music.txt`: Git blob
  `63f281f1d38b571c39d680983e673d90fb580686`, size `3857`, decoded SHA-256
  `c0005b460c3f9d9caacf3a630de150b963fe0a2f34cf8453de84459132c36897`
- `README.md`: Git blob `8b25a903180ab977e826cabefa95766683ea3d6a`,
  size `4791`, decoded SHA-256
  `5e93341a5015e23d777a800733bb8342f3d56271986c4d9244c3c32050ae294a`
- `LICENSE.txt`: Git blob `882c00a1630fa7d25421af1aacc56bba2244f0a7`,
  size `52563`, decoded SHA-256
  `260270432dabb1653c0944a1091adc827711fccd0f1af636156a247d4b9abd0a`

The per-asset attribution file identifies Storyteller as the author of each of
the six tracks and marks each one only `GPL`. The same immutable repository's
legal section assigns GNU GPL version 2 or later to the server, Java client,
and Android client, but it does not explicitly include `data/music` in that
scope. `LICENSE.txt` supplies GPL version 2 text without resolving whether the
music grant is version 2 only, version 2 or later, or another GPL version.
Therefore no exact SPDX expression is established for these works.

## Exact source identity

| Logical path | Atrinik source SHA-256 | Repository path | Git blob |
| --- | --- | --- | --- |
| `background/deep_forest.ogg` | `ca4c5ba437ba7fa1bb20e87474348ca67e271a963c040bdd00e19015063e9acb` | `data/music/deep_forest.ogg` | `94aa2bbc66545b6d7ce20dd2961a67c6120d1132` |
| `background/dungeon_entrance.ogg` | `b3e04539527fcc64562cd02057d67cf01218ce92c513c0a85cc3e7853ab1dc0c` | `data/music/dungeon_entrance.ogg` | `48d587b662cac8e2ec10d0340fc8619e99422054` |
| `background/mystical_aura.ogg` | `04f8be579aced562790ef0851ec83ec4f42a6cf6063f765155c40962c58b1d38` | `data/music/mystical_aura.ogg` | `4dc3ac7e41d2d47ea9d4af21f22d50c1160f986e` |
| `background/new_hope.ogg` | `39d4e4c1f6d2bd2578cfcb1b9e0532f149330754e00bf6548fce2007d37c68a4` | `data/music/new_hope.ogg` | `beb6fad55a57151dc6a10746e1594198fc41a0f1` |
| `background/sacred_moments.ogg` | `6bf6488fa093b21d34697afaba3f75ae69656569f7851fad6a60cbd9bbddb7ac` | `data/music/sacred_moments.ogg` | `99d3f6e43eb47ec90781dddbd50fb7fb415d9ce3` |
| `background/magical_tower.ogg` | `c17a3122fd35c0908a5c30da0f8d604838b18f17c0c7057c688b0a790af86a69` | `data/music/the_magical_tower.ogg` | `57d0d3860ca1a4e305a277f530a31b4703a3c612` |

Each local file's Git blob is exactly the named authoritative repository blob;
the SHA-256 values bind the same bytes in the Atrinik source manifest.

For each exact track, `background/LICENSE` preserves Storyteller's supplied
author identity, the immutable repository source coordinate, and an indication
that Atrinik converts the preserved Vorbis input to Opus. The generated source
manifest binds the complete heading-and-asset-line notice hash, so attribution
or modification-notice drift makes the manifest stale.

## Decision

The six exact inputs above remain blocked until an authoritative grant
explicitly establishes the GPL version and scope for the music, or permission
is obtained. The other eight Stendhal-noticed files also lack exact current
source identity. No Stendhal candidate is eligible for critical listening.
Any byte, notice, path, attribution, grant, or upstream-coordinate change
requires a new review.
