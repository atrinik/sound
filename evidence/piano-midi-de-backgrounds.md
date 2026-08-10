# piano-midi.de background license review

Reviewed 2026-08-10 for the 25 `background/*.mid` files attributed to
piano-midi.de in `background/LICENSE`.

## Authoritative grant

The preserved first-party response at
`evidence/captures/piano-midi-de-copy-20160409000057.html` was retrieved from
<https://web.archive.org/web/20160409000057id_/http://www.piano-midi.de:80/copy.htm>.
Its SHA-256 is
`9675b087f9cf38bba94c7edd3ea0827fb13d42452168a453f6a3823d58603078`,
its SHA-1 is `0a2a236d97334ef68d681a27602de1a16259ba7a`, and the
Internet Archive CDX payload digest is
`BIVCG3MXGNHPNDLIDITWALPBUFRFTOT2`, the base32 encoding of that SHA-1.
The page identifies Bernd Krueger as the author of the site's MIDI files,
permits use and adaptation with attribution, and requires distribution under
the same Creative Commons BY-SA Germany 3.0 conditions.

The exact SPDX identity is `CC-BY-SA-3.0-DE`, not the unported
`CC-BY-SA-3.0`. The packaged legal text is pinned to SPDX license-list-data
commit `5bf6d9610255540bfbee6890765a616042bf1e11`, blob
`472c3663af551687c998b38779e059956bf26e0b`, and SHA-256
`dfac6ca9c9b3082919f8e417e522e561e11c8402eab83e1099650b8e4347412d`.

## Exact asset identity

The following immutable replay coordinates preserve responses from the
licensor's first-party URLs. For every row, the CDX digest is the base32
encoding of the local file's recomputed SHA-1; the local SHA-256 is also bound
by the review ledger. The four historical variants (`elise.mid`,
`fountain.mid`, `pearls.mid`, and `thunderstorm.mid`) were additionally raw
replayed and byte-compared during this review. Tonejs/Midi commit
`3946ba0d931755bbe782b7c184dca5939f54589d` remains corroborative only and is
not used as the authoritative grant or source identity.

| Local file | Archived first-party response (`https://web.archive.org/web/{timestamp}id_/{original}`) | CDX digest | Local SHA-256 |
| --- | --- | --- | --- |
| `autumn.mid` | `20101128063527` / `http://piano-midi.de/midis/tchaikovsky/ty_oktober.mid` | `BC7PLTGV47OPUD2LAE546736MVM4E727` | `4d0b91ac3351ef942b6852a0ed27cd1f9e3690960c6a9cffb8a37530e5cec2aa` |
| `barcarolle.mid` | `20130501142630` / `http://piano-midi.de/midis/tchaikovsky/ty_juni.mid` | `2ZPF4HM7XRGWXLJVVDDBLYIJG5YNV5P2` | `77dc5d00e24245e0b62bf735e9076e4e47892a272a773ae716a671245b502dbc` |
| `carnival.mid` | `20101128063432` / `http://piano-midi.de/midis/tchaikovsky/ty_februar.mid` | `JFZTVYF52RC32YNCCVNTONQH5RSANG5Z` | `b66b57e1d7575ef7d8ab492a139fe1b0058c2b97c514aee57761352de74721f5` |
| `christmas1.mid` | `20130602134842` / `http://piano-midi.de/midis/xmas/bk_xmas1.mid` | `YBT4CYVP5TIPJBGNTALYQCNCPXYYIOVL` | `f17f2d784214bbf7444b29b3aea3ae2415c3d32e8fb1ed2ebefde40f04a8d84b` |
| `christmas2.mid` | `20101128083530` / `http://piano-midi.de/midis/xmas/bk_xmas2.mid` | `DJCVIND64XFB62SEMGYY5DJFC6O35EL4` | `aba4c8a944c39d577041d36c8597acc467a1f159f511551a6d1a18fc516f49c0` |
| `christmas3.mid` | `20130602121908` / `http://piano-midi.de/midis/xmas/bk_xmas3.mid` | `JF2KDJZKHVC4NX722N7WKJZ6IOIYISHV` | `61b4c298d74773ba31daf4ca02adf1f705fad5de83b07a654e451a13786396fc` |
| `christmas4.mid` | `20130602122350` / `http://piano-midi.de/midis/xmas/bk_xmas4.mid` | `WQBXQRJNNUERW2SKFDG7QD27GGGDGYKH` | `51af00441887b3809e59aad29170704b8bf2193bff9f735168d4c40c355ef09c` |
| `christmas5.mid` | `20130602133657` / `http://piano-midi.de/midis/xmas/bk_xmas5.mid` | `6OCW6TBS62KHWTEO5ZY3H7XDLJYXR7EV` | `1d8fc5736afdc94a8030654f1445ca93fa5ae9207617b4e4810d703a873ae7d0` |
| `christmas6.mid` | `20130501123004` / `http://piano-midi.de/midis/tchaikovsky/ty_dezember.mid` | `Q4BOZZEG3UIIS7ILZJVSGHXOFK7QZ5HR` | `589423e4a27d00e6a6e59bc466bf99b06c0a68fe697f0d0d57e4311cb362797b` |
| `elise.mid` | `20051211143909` / `http://www.piano-midi.de:80/midis/beethoven/elise.mid` | `466R4QKNYD5RUCJVYF232Y3EOXKHMRHG` | `f26dee755a2eb52c993784fef76bd1a1038c2b9f9c3a5b5e3f28566dd837cc73` |
| `fireside.mid` | `20101128063316` / `http://piano-midi.de/midis/tchaikovsky/ty_januar.mid` | `2Q53BFDJ4SJ2PZH7E37M4HRWH2N7G2HN` | `2e8a458db9fef6dd05960b494767e2117797a3788e699e0a80fe9e0d51bc1670` |
| `fountain.mid` | `20060214024707` / `http://www.piano-midi.de:80/midis/burgmueller/burg_quelle.mid` | `DAT4XDESU54MPKRHWBPIN76PIQPE726O` | `e0ec646d7ae4100ed4298d6bcabc15a3b91238f53d476de41632c044670b212b` |
| `harvest.mid` | `20101128063601` / `http://piano-midi.de/midis/tchaikovsky/ty_august.mid` | `RKC6HDC57QC2Z4JJNU2FUHPG4RIQN4O3` | `1de42ed86051fa47f3528b4860834909b774a485e16c03e04ae00e801259a2e5` |
| `lark.mid` | `20130501133240` / `http://piano-midi.de/midis/tchaikovsky/ty_maerz.mid` | `2DLFO5PBYORWY4U53E6JTDAG5EI7GCSF` | `89f313d23b0574d212f912c6c4892260092b808077a8576adc741ee8866e40ed` |
| `pearls.mid` | `20060214024701` / `http://www.piano-midi.de:80/midis/burgmueller/burg_perlen.mid` | `BBQGJOSOKFIELYU47FKR75I5Y4HXGQMU` | `a5891a46c756f1654b954312b0d1cc8380409d034c8069a0954482bc9fa773af` |
| `prelude1.mid` | `20051106043322` / `http://www.piano-midi.de:80/midis/bach/bach_846.mid` | `O5M3TGSHC4K3UAGV22HXFR5YHVD2EXJJ` | `107f2b6a298f283f8d26d4e8359669e7780f7ea64011b7844f2ed066d874a37e` |
| `prelude2.mid` | `20051106042842` / `http://www.piano-midi.de:80/midis/bach/bach_847.mid` | `UHKM4GXAFTRLVO4REVDVPNRH4VKQF3VG` | `6a5a582455fee99765fd3c920810b36f1a4d7a991d7e93e74f072fc060faf0bf` |
| `prelude3.mid` | `20051106042906` / `http://www.piano-midi.de:80/midis/bach/bach_850.mid` | `ALJTLIPWUSBPP5MSUSSQITNYVZKBLXPR` | `cfaf4db14b0f5f57f056211407aac26df8511e93afd00a6f581fda6cdfec9812` |
| `reaper.mid` | `20101128063453` / `http://piano-midi.de/midis/tchaikovsky/ty_juli.mid` | `5ZV36DODV7UXA47FHRZUSV4SAOIHBBO2` | `0f07ca3b168a4ea5213a806c6e31a000316c3f41ce171ba1168e0ff8d71274e7` |
| `ride.mid` | `20101128063350` / `http://piano-midi.de/midis/tchaikovsky/ty_november.mid` | `7V2Y7FA5MVTAIV34KJIDVUEIXEACRMMN` | `c7172ee9287e68b32e93543516524d983d9a37d5ce2393c953882be84e01b713` |
| `snowdrop.mid` | `20101128063235` / `http://piano-midi.de/midis/tchaikovsky/ty_april.mid` | `4SKD5JVG7FBGIIOPFG7ND5HOFE3OVLI5` | `251f52b91abfb44352944c8f5bee1434b6621577cb7a8a4c10860b262a397ff5` |
| `starlight.mid` | `20101128063415` / `http://piano-midi.de/midis/tchaikovsky/ty_mai.mid` | `JK3XMGEXMLQMPPXVBR42LXUCF6RHNJC7` | `e68444752e6a2a994fedb2cb3a2ca7e596501764993f445b35cf1b3387b35469` |
| `tango.mid` | `20101219053022` / `http://piano-midi.de/midis/godowsky/god_alb_esp2.mid` | `FHAY6JJVU5NWQ56SHIIWZI5EQEWEYA6E` | `b7a2087c004ea47f1c52443ae184fb901d698ea87b7396140c405c2206cbd12a` |
| `the_hunt.mid` | `20101128063545` / `http://piano-midi.de/midis/tchaikovsky/ty_september.mid` | `4LFBHVEWZND56ZAGW7V4ZN3T2VLZELPS` | `59f8664327c66e2566ea725387904caf61b96f1b1436ac5d33991f0d62eac60b` |
| `thunderstorm.mid` | `20060214024732` / `http://www.piano-midi.de:80/midis/burgmueller/burg_gewitter.mid` | `MA7STFHG73V732HGRMY3PUQVSLJMINMM` | `fc2295124ee88dbcd1117290070af69486553f5b2540443374549e17b22b80b3` |

## Decision

Approve all 25 files as `CC-BY-SA-3.0-DE`. The archived first-party grant
establishes the license and attribution requirements, and the archived
first-party asset payload digests bind every local file to the granted set.
The packaged notice preserves Bernd Krueger's identity, supplied work title,
copyright statement, source, same-license condition, and the dated Atrinik
MIDI-to-Opus modification. Each ledger record binds the exact source, evidence,
license, and packaged heading-and-line bytes.
