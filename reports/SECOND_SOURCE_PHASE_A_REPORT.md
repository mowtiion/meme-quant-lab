# Tweede bron: drie historische blokken — 24 september 2026

De drie aangeleverde ruwe Helius-blokresponses zijn **opnieuw gehasht en vergeleken**
met de bevroren primaire referentie: **MATCH** voor slots 447000000–447000002.
De ZIP bevat exact drie blokbestanden en het eerdere vergelijkingsrapport; de
ZIP-integriteitscontrole slaagt. De drie blokken bevatten samen
3.841 transacties. Voor elk blok meldt het script gelijke header, signatures,
versies, transactie-instructies, uitvoeringsmetadata, inner instructions, logs,
loaded addresses, SOL-/tokenbalansen en de volledige canonieke JSON-resultaatboom.
Alle 27 veldgroep-hashes zijn hier opnieuw berekend en sluiten aan op de referentie.

| Slot | Transacties | Veldgroepen | Door Helius gerapporteerde raw SHA-256 |
|---|---:|---:|---|
| 447000000 | 1.256 | 9/9 gelijk | `685cbb1650604949690712a87df76cdf9f645a2e0482373ab66c64892f6a4674` |
| 447000001 | 1.216 | 9/9 gelijk | `5a0f66b476b4825c332fd8df389e397d6d5e549264e375c60c43f3808090b7e0` |
| 447000002 | 1.369 | 9/9 gelijk | `504394244fed288f11c0a0e02770a3f5f0be71977f823dc1a3caed6fef0539b8` |

Het rapport vermeldt vier read-only verzoeken en 14.844.064 ontvangen bytes, onder
de vooraf gestelde grenzen. Het verwijst naar het bevroren primaire manifest
`2b1a82e1062f068ff884a34b34ca1c7c94400fa99bba4fa7fffafca9f7695683`.
De aangeleverde originele rapportbytes hebben SHA-256
`2aca98e6caa70cc7ee7b10fa2dff1b51ffdee083e0de7c0386076195ff75ce01`.
Het gevalideerde rapport staat in
`experiments/exp000/helius-phase-a-user-report.json`.
De herberekende controles staan in
`experiments/exp000/helius-phase-a-verification.json`. De uitvoer is reproduceerbaar
met `scripts/verify_second_source_archive.py` en het ontvangen ZIP-bestand.
Het ontvangen ZIP-archief is 2.840.223 bytes en heeft SHA-256
`12a08e6f4b61c62daa4bdcf93cf7dbec898b4b376dd39a48e71fc9f18387c94e`.
De drie ruwe blokbestanden samen zijn 14.843.999 bytes; de resterende 65 bytes in het
opgegeven netwerkbudget horen bij het aparte `getBlocks`-antwoord. Elk van de drie
blokbestand-hashes matcht het eerder ontvangen rapport. De responsbestanden en het
oorspronkelijke rapport staan samen in het aangeleverde archief, buiten Git.

**Bewijsgrens:** dit zijn twee afzonderlijke RPC-endpoints met gelijksoortige
historische blokresponses. De onafhankelijkheid van hun onderliggende upstream
is niet vastgesteld, en drie blokken bewijzen geen volledige historische census.
EXP-000 blijft FAIL.

Voor de 41 overige proefslots is de omvang op basis van primaire raw responses
140.090.475 bytes (maximaal 7.984.212 per blok). Een apart plan moet maximaal
42 requests, 192 MiB responsebudget en 600 seconden looptijd toestaan en binnen
het gratis Helius-quotum blijven. Deze schaalproef is nog niet uitgevoerd. Het
[testprotocol](../docs/SECOND_SOURCE_CHECK.md) legt die grens vast.
