# piano-midi.de background provenance and license review

Reviewed 2026-08-10 for the 25 `background/*.mid` files attributed to
piano-midi.de in `background/LICENSE`.

## Authoritative grant

The first-party page at <http://piano-midi.de/copy.htm> identifies Bernd
Krueger as the author of the site's MIDI files, permits their use and
adaptation with attribution, and requires distribution under the same Creative
Commons BY-SA 3.0 Germany conditions. The page retrieved for this review has
SHA-256 `f1d21ef436e63e11e7d48b6eabb25c2b5c423d4c06bbda99ab3a13d65a582135`.
The same statement is preserved at Tonejs/Midi commit
`3946ba0d931755bbe782b7c184dca5939f54589d`, blob
`954f989917748976b81e075921e5421a1c30896d`, with decoded SHA-256
`fc51bc6b888cc501a15f942e0f1f7edb792077e104e3044f80cc108e7164c1b6`.

The exact SPDX identity is `CC-BY-SA-3.0-DE`, not the unported
`CC-BY-SA-3.0`. The packaged legal text is pinned to SPDX license-list-data
commit `5bf6d9610255540bfbee6890765a616042bf1e11`, blob
`472c3663af551687c998b38779e059956bf26e0b`, and SHA-256
`dfac6ca9c9b3082919f8e417e522e561e11c8402eab83e1099650b8e4347412d`.

## Exact asset identity

Each reviewed local file embeds Bernd Krueger's copyright identity and the
work title. Twenty-one are byte-identical to the current first-party download.
The remaining four (`elise.mid`, `fountain.mid`, `pearls.mid`, and
`thunderstorm.mid`) identify the same author and work as the linked current
first-party file but are earlier authored revisions; the first-party grant
covers Bernd Krueger's MIDI files without limiting it to the latest revision.

| Local path | Local SHA-256 | First-party path | Identity |
| --- | --- | --- | --- |
| `background/autumn.mid` | `4d0b91ac3351ef942b6852a0ed27cd1f9e3690960c6a9cffb8a37530e5cec2aa` | `midis/tchaikovsky/ty_oktober.mid` | byte-identical |
| `background/barcarolle.mid` | `77dc5d00e24245e0b62bf735e9076e4e47892a272a773ae716a671245b502dbc` | `midis/tchaikovsky/ty_juni.mid` | byte-identical |
| `background/carnival.mid` | `b66b57e1d7575ef7d8ab492a139fe1b0058c2b97c514aee57761352de74721f5` | `midis/tchaikovsky/ty_februar.mid` | byte-identical |
| `background/christmas1.mid` | `f17f2d784214bbf7444b29b3aea3ae2415c3d32e8fb1ed2ebefde40f04a8d84b` | `midis/xmas/bk_xmas1.mid` | byte-identical |
| `background/christmas2.mid` | `aba4c8a944c39d577041d36c8597acc467a1f159f511551a6d1a18fc516f49c0` | `midis/xmas/bk_xmas2.mid` | byte-identical |
| `background/christmas3.mid` | `61b4c298d74773ba31daf4ca02adf1f705fad5de83b07a654e451a13786396fc` | `midis/xmas/bk_xmas3.mid` | byte-identical |
| `background/christmas4.mid` | `51af00441887b3809e59aad29170704b8bf2193bff9f735168d4c40c355ef09c` | `midis/xmas/bk_xmas4.mid` | byte-identical |
| `background/christmas5.mid` | `1d8fc5736afdc94a8030654f1445ca93fa5ae9207617b4e4810d703a873ae7d0` | `midis/xmas/bk_xmas5.mid` | byte-identical |
| `background/christmas6.mid` | `589423e4a27d00e6a6e59bc466bf99b06c0a68fe697f0d0d57e4311cb362797b` | `midis/tchaikovsky/ty_dezember.mid` | byte-identical |
| `background/elise.mid` | `f26dee755a2eb52c993784fef76bd1a1038c2b9f9c3a5b5e3f28566dd837cc73` | `midis/beethoven/elise.mid` | embedded-author earlier revision |
| `background/fireside.mid` | `2e8a458db9fef6dd05960b494767e2117797a3788e699e0a80fe9e0d51bc1670` | `midis/tchaikovsky/ty_januar.mid` | byte-identical |
| `background/fountain.mid` | `e0ec646d7ae4100ed4298d6bcabc15a3b91238f53d476de41632c044670b212b` | `midis/burgmueller/burg_quelle.mid` | embedded-author earlier revision |
| `background/harvest.mid` | `1de42ed86051fa47f3528b4860834909b774a485e16c03e04ae00e801259a2e5` | `midis/tchaikovsky/ty_august.mid` | byte-identical |
| `background/lark.mid` | `89f313d23b0574d212f912c6c4892260092b808077a8576adc741ee8866e40ed` | `midis/tchaikovsky/ty_maerz.mid` | byte-identical |
| `background/pearls.mid` | `a5891a46c756f1654b954312b0d1cc8380409d034c8069a0954482bc9fa773af` | `midis/burgmueller/burg_perlen.mid` | embedded-author earlier revision |
| `background/prelude1.mid` | `107f2b6a298f283f8d26d4e8359669e7780f7ea64011b7844f2ed066d874a37e` | `midis/bach/bach_846.mid` | byte-identical |
| `background/prelude2.mid` | `6a5a582455fee99765fd3c920810b36f1a4d7a991d7e93e74f072fc060faf0bf` | `midis/bach/bach_847.mid` | byte-identical |
| `background/prelude3.mid` | `cfaf4db14b0f5f57f056211407aac26df8511e93afd00a6f581fda6cdfec9812` | `midis/bach/bach_850.mid` | byte-identical |
| `background/reaper.mid` | `0f07ca3b168a4ea5213a806c6e31a000316c3f41ce171ba1168e0ff8d71274e7` | `midis/tchaikovsky/ty_juli.mid` | byte-identical |
| `background/ride.mid` | `c7172ee9287e68b32e93543516524d983d9a37d5ce2393c953882be84e01b713` | `midis/tchaikovsky/ty_november.mid` | byte-identical |
| `background/snowdrop.mid` | `251f52b91abfb44352944c8f5bee1434b6621577cb7a8a4c10860b262a397ff5` | `midis/tchaikovsky/ty_april.mid` | byte-identical |
| `background/starlight.mid` | `e68444752e6a2a994fedb2cb3a2ca7e596501764993f445b35cf1b3387b35469` | `midis/tchaikovsky/ty_mai.mid` | byte-identical |
| `background/tango.mid` | `b7a2087c004ea47f1c52443ae184fb901d698ea87b7396140c405c2206cbd12a` | `midis/godowsky/god_alb_esp2.mid` | byte-identical |
| `background/the_hunt.mid` | `59f8664327c66e2566ea725387904caf61b96f1b1436ac5d33991f0d62eac60b` | `midis/tchaikovsky/ty_september.mid` | byte-identical |
| `background/thunderstorm.mid` | `fc2295124ee88dbcd1117290070af69486553f5b2540443374549e17b22b80b3` | `midis/burgmueller/burg_gewitter.mid` | embedded-author earlier revision |

## Decision

These exact 25 source hashes have full-work conversion and redistribution
permission under `CC-BY-SA-3.0-DE`. Runtime attribution must retain Bernd
Krueger's name, <http://www.piano-midi.de>, and the same-license condition.
