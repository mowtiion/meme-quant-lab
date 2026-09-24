# Tweede bron: drie historische blokken — 24 september 2026

De door de gebruiker lokaal uitgevoerde Helius-proef meldt **MATCH** voor slots
447000000–447000002. Het aangeleverde rapport is gecontroleerd op schema, bereik,
budget, referentiemanifest en alle 27 veldgroepen. De drie blokken bevatten samen
3.841 transacties. Voor elk blok meldt het script gelijke header, signatures,
versies, transactie-instructies, uitvoeringsmetadata, inner instructions, logs,
loaded addresses, SOL-/tokenbalansen en de volledige canonieke JSON-resultaatboom.

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

**Bewijsgrens:** de drie ruwe Helius-blokresponses staan momenteel op de computer
van de gebruiker en zijn hier nog niet ontvangen. Daarom is dit een geverifieerd
schema van een lokaal scriptresultaat, geen onafhankelijke herberekening van die
drie Helius-payloads in deze werkruimte. Een Helius-endpoint is bovendien pas
een onafhankelijke bron als diens upstream-onafhankelijkheid is vastgesteld.
De proef is geen volledige historische census en maakt EXP-000 niet geldig.

Volgende controle: importeer de drie raw blokbestanden als archief, verifieer elk
tegen de gerapporteerde raw SHA-256 en herbereken alle veldgroep-hashes hier.
Schaal daarna pas onder een apart budget op naar de 41 proefslots. Het
[testprotocol](../docs/SECOND_SOURCE_CHECK.md) legt die grens vast.
