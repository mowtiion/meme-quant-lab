# EXP-000 — herstel van afgebroken eventlogs

**Herstel geïmplementeerd. EXP-000 blijft FAIL; de 1.000-launch-pilot is niet vrijgegeven.**

Broncode: `38fea1685405e412ce1a2b86e472f7d62203dbde`, schone werkboom bij beide replays.
[GitHub Actions: geslaagd](https://github.com/mowtiion/meme-quant-lab/actions/runs/35776709066).
75 tests slagen, waarvan 21 nieuwe CPI-hersteltests. Geen nieuwe RPC-download of betaald gebruik.

## Wat is hersteld

De twee historische transacties bevatten Anchor-eventgegevens in zelfaanroepen van PumpSwap.
De decoder bouwt daaruit één geordende stroom, controleert die tegen aanwezige logs en neemt
alleen events met voldoende bewijs voor succesvolle uitvoering op. De event-authority-account
moet overeenkomen met de account in de gedecodeerde ouderinstructie; programma, stackHeight,
ouderrelatie, eventtype en payload worden eveneens gecontroleerd.

| Slot | Transactie | Bevestigde BuyEvents | Ontbrekende log hersteld | Resterend issue |
|---|---|---:|---:|---|
| 447000000 | `3rdwGVet…HPekFhz` | 2 | 0 | Geen voor de gevalideerde doelinstructies |
| 447000002 | `5vX8MjHD…2nFSJE` | 1 | 1 | Onbewezen uitvoering van administratief event |

De eerste transactie had beide koop-events al in de logs. De CPI-kopieën bevestigen ze;
ze worden niet nogmaals toegevoegd. De tweede transactie mist een BuyEvent, maar heeft
succeslogs van de event-CPI en de koopinstructie. De buitenste Jupiter-instructie moet
zijn geslaagd omdat de gehele transactie geslaagd is. Dat levert voldoende uitvoeringsbewijs.

Het herstelde event op instructiepad `[8,14]`, onder koopinstructie `[8,7]`, bevat
947.612.248.707 base-eenheden en 905.904 quote-eenheden, beide raw integers.
Dit zijn eventbedragen, geen gevalideerde uitvoeringsprijs of netto cashflow inclusief fees.
Volledige signatures, payloads, raw hashes en instructiepaden staan in de testfixtures en exports.

Een later `CloseUserVolumeAccumulatorEvent` op `[8,16]` heeft geen succesbewijs voor
zichzelf of zijn inner-ouderinstructie. Een router kan een inner-fout opvangen: succes van
alleen de gehele transactie bewijst dit administratieve event dus niet. De kandidaat blijft
als `CPI_EXECUTION_UNPROVEN` in issues, inclusief payload en herkomst. Hij wordt geen trade
of bevestigd decoded event. Zonder aanvullend uitvoeringsbewijs of gevalideerde historische
programmasemantiek wordt dit issue niet verwijderd.

## Resultaten van de volledige herhaling

| Run | Events | Wallettrades | Protocolacties | Decoded events | Issues |
|---|---:|---:|---:|---:|---:|
| real-pilot-v4 — 41 blokken | 3.082 | 3.072 | 3 | 3.258 | 0 |
| archive-preflight-v3 — 3 blokken | 168 | 165 | 2 | 175 | 1 |

De archiefproef had eerder 167 events, 164 trades en vier issues: twee truncatiemeldingen
plus twee open stacks. Deze zijn vervangen door drie geverifieerde CPI-events (twee bekende,
één nieuw) en één expliciet onbevestigde kandidaat. Er verdwijnen geen bestaande economische
events; de enige toevoeging is de ontbrekende koop. De datasetversie van de oorspronkelijke
41-blokkenproef blijft gelijk. De nieuwe archiefversie is
`260231a35dca90c12b42befce65f04c567843cc468abc37678f52e60bea6160a`.

Per run zijn alle zes JSONL-, Parquet- en DuckDB-tabellen inhoudelijk gelijk, inclusief
herkomst en grote integerbedragen. Beide databases zijn zelfstandig leesbaar zonder WAL.
De twee nieuwe fixtures komen exact overeen met transacties in de originele raw blokken.
Bewijs: [CPI_RECOVERY_VERIFICATION.json](CPI_RECOVERY_VERIFICATION.json).

## Geteste grenzen

De tests vergelijken CPI- en logpayloads van vier volledige echte transacties, inclusief drie
protocol buy-and-burn-acties, en simuleren ontbrekende eventlogs. De economische classificatie
en bedragen blijven gelijk. De twee echte afgebroken transacties zijn afzonderlijke regressies.
Negatieve controles dekken payloadtegenspraak, foutieve programma's/autoriteit/discriminators,
niet-zelfaanroepen, ontbrekende of foutieve stackHeight, negatieve accountindices, ontbrekende
metadata, dubbele instructiegroepen/CPI's, onbekend uitvoeringssucces en teruggedraaide ouders.

Het herstel is beperkt tot de beschreven PumpSwap-instructievarianten. Dit bewijst geen volledige
historische IDL/deployment-mapping. Nieuwe varianten en onbewijsbare gevallen blijven blockers.
Bij herstel wordt de hele doel-eventstroom van de transactie vervangen; event_index wordt de
instructie-preorderpositie. Daarom kunnen event-ID's tegenover oude logdatasets veranderen.
Oude en nieuwe datasets mogen niet blind worden samengevoegd. Zie [SCHEMAS](../docs/SCHEMAS.md).

## Vervolg

De volgende onderzoeksstap is het reconciliëren van create-instructies met CreateEvents,
een onafhankelijke censusbron en historische deployment-/IDL-versies. Parallel daaraan blijft
het onbevestigde administratieve event een zichtbaar open punt. Daarna volgen de economische
ledgers en een begrensd downloadplan. Zes launches uit twee korte proefvensters vormen nog
geen complete populatie; snapshots en follow-up zijn onvoldoende gedekt.

`python -m meme_quant.cli preflight --report experiments/exp000/archive-preflight-v3.json`
geeft terecht BLOCKED (exitcode 2). Geen modellering of live trading gestart.

## Primaire technische bronnen

- [Anchor: emit_cpi en eventgegevens in inner instructions](https://www.anchor-lang.com/docs/features/events).
- [Anchor-broncode: EVENT_IX_TAG](https://docs.rs/anchor-lang/latest/src/anchor_lang/event.rs.html).
- Vastgelegde PumpSwap-IDL in `vendor/pump_amm.json`; hash en bron in `vendor/provenance.json`.
