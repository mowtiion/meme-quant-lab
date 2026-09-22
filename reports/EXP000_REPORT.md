# Meme Quant Lab — EXP-000 review, 22 september 2026

**Status: FAIL. Geen vrijgave voor EXP-001. De pilot met 1.000 echte launches is niet uitgevoerd.**

## Gecontroleerd en hersteld

- Alle 35 oorspronkelijke GitHub-bestanden waren byte-identiek aan de lokale bestanden.
- De lokale werkbranch is opnieuw gebaseerd op de GitHub-historie. Oudere lokale commits blijven behouden.
- 54 tests slagen lokaal en in GitHub Actions, inclusief 14 nieuwe regressie-/opslagcontroles.
- Alle 52 raw-objecten (154.946.176 bytes) hebben de verwachte SHA-256-hash.
- Beide vendor-IDL's komen overeen met de hashes in `vendor/provenance.json`.
- De laatste drie runs bevatten elk zes overeenkomende JSONL/Parquet/DuckDB-tabellen.
  De databases zijn na een expliciete checkpoint zelfstandig leesbaar, zonder WAL-bestand.
- Een eerste herhaling (`real-pilot-v2`) bleek bij controle een onvolledige zelfstandig leesbare
  DuckDB-export te hebben. Die run wordt vervangen door `real-pilot-v3`; oude output is niet overschreven.
- De 1.000-launch-gate kan niet meer slagen door `sample_size` onder 1.000 te zetten.
- Replay weigert manifests met een andere commitment dan finalized.
- Events uit een mislukte inner-programma-aanroep worden teruggedraaid, ook als een router de fout opvangt.

Broncode van de definitieve runs: `95d2e4dd405aabc4ae60cf665c4533d23f3a1748`, schone werkboom.
[Geslaagde CI-run](https://github.com/mowtiion/meme-quant-lab/actions/runs/35738444376).

## Drie oorspronkelijke AMM-fouten opgelost

De events op slots 449382008, 449382021 en 449382027 behoren tot de instructie
`boost_buy_and_burn`. Dit blijkt uit de vastgelegde officiële IDL, de instructieaccounts,
het bijbehorende `BoostBuyAndBurnEvent`, de SPL-burninstructie en de pre/post-tokenbalansen.

| Slot | Verbrande base-eenheden (raw) | Gebruikte quote-eenheden (raw, SOL-lamports) |
|---|---:|---:|
| 449382008 | 97.841.686.487 | 358.886.388 |
| 449382021 | 175.892.295.483 | 781.595.681 |
| 449382027 | 230.676.585.266 | 694.587.958 |

Per actie sluiten pool-base, pool-quote en boost-vault-balansmutaties exact aan op de bedragen.
De normalisatie bewaart één `protocol_buy_burn`-event met een verwijzing naar het companion-event;
beide oorspronkelijke logevents blijven in `decoded_events` en raw bewaard.
Deze acties tellen niet mee in walletkopers, koopvolume of trade-mark-outcomes.
Ze beïnvloeden wel de markt; de volledige economische ledger blijft daarom een aparte open gate.

De tests wijzen ontbrekende companions, ontbrekende burninstructies, afwijkende mints/bedragen,
balansverschillen en ambigue meerdere buys af. Multi-action-transacties worden bewust niet gegokt.
De controle reconcilieert deze transacties; zij bewijst geen volledige historische supply-/pool-ledger.

[Officiële PumpSwap-IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump_amm.json).
De gebruikte bytehash staat in de provenance; deployment-slots zijn nog niet gevalideerd.

## Nieuwe resultaten

| Run | Echte launches / steekproef | Wallettrades | Protocol buy-and-burn | Issues | Snapshots / outcomes |
|---|---:|---:|---:|---:|---:|
| real-pilot-v3, 41 blokken | 5 / 5 | 3.072 | 3 | 0 | 25 / 125 |
| archive-preflight-v2, 3 blokken | 1 / 1 | 164 | 2 | 4 | 5 / 25 |
| synthetic-smoke-v3 | 0 echt; 1.000 uit 1.200 kunstmatig | 3.840 kunstmatig | 0 | 0 | 5.000 / 25.000 |

De oorspronkelijke proef beslaat 2026-09-22 12:42:04–12:42:15 UTC, dus circa elf seconden.
De archiefproef betreft slots 447000000–447000002 vanaf 2026-09-14 16:31:33 UTC.
De zes echte launches zijn afkomstig uit twee losse, korte vensters en vormen geen representatieve census.

De archiefdownload via publieke RPC was gratis en volledig voor de drie geselecteerde blokken.
Twee geslaagde transacties bevatten echter `TRUNCATED_LOGS` en `UNCLOSED_LOG_STACK`:

- `3rdwGVetQhGTTUkZAeWwncchTW5P2mAB1SD5KfzWGwMooRFuMoyBKT7wGJsEywo2SXZcHYxf2ZYNrwhn7HPekFhz`
- `5vX8MjHDo7gYSSKHym3DpjHs7Vjnkie1PnyZjrwdifdPA3JT2WTNBYVhrJzvm1tzLh5awnpKt3H8ArF5jm2nFSJE`

Beide transacties verwijzen naar PumpSwap. De 4 issues zijn dus 2 getroffen transacties,
geen 4 afzonderlijke transacties. Inner-instructies zijn aanwezig; herstel via CPI-events
moet nog worden geïmplementeerd en op volledigheid, volgorde en dubbeltelling worden getest.
Een ontbrekende log is geen bewijs dat er geen transactie/event plaatsvond.

## Gatebesluit en vervolg

| Onderdeel | Status |
|---|---|
| Hashes en download van de geselecteerde blokken | PASS voor deze proeven |
| Decode/normalisatie oorspronkelijke 41 blokken | PASS na protocolclassificatie |
| Decode/normalisatie historische archiefproef | FAIL: afgebroken logs |
| Volledige historische launchpopulatie / 1.000 launches | FAIL |
| Historische IDL/regime-mapping en reserve/transfer-ledger | FAIL |
| Vijf volledig gedekte snapshots per launch | FAIL |
| Gevalideerde entryreference en zeven dagen follow-up | FAIL |
| Modellering / voorspellende edge | Niet gestart / niet aangetoond |

`configs/pilot1000.json` legt de beoogde creatieperiode vast: 14 september 2026 UTC,
met follow-up tot 22 september 00:05 UTC en seed 20260922. De readiness-controle eindigt
terecht met `BLOCKED` (exitcode 2). Er is geen betaald endpoint aangeschaft en geen bulkdownload gestart.

Eerst afgebroken logs herstellen en de volledige census, historische regimes en ledger op een
begrensde export valideren. Vervolgens de downloadomvang bepalen, de census vastzetten en daaruit
1.000 launches trekken. Het masterbrief verlangt dat essentiële integriteitsfouten worden
opgelost voordat EXP-001 begint. Alleen groene softwaretests zijn daarvoor onvoldoende.

## Herleidbaarheid

Runrapporten: `experiments/exp000/{real-pilot-v3,archive-preflight-v2,synthetic-smoke-v3}.json`.
Controlebewijs: `reports/REVIEW_VERIFICATION.json`. Oudere runrapporten blijven in het experimentregister.

- Oorspronkelijk raw-manifest: `e6f27b744a0dcd838d24de1b916109ac8cd744cdf2103871bc2592d0f90413b5`.
- Archief raw-manifest: `2b1a82e1062f068ff884a34b34ca1c7c94400fa99bba4fa7fffafca9f7695683`.
- Beide staan als `<hash>.json` in `data/raw/manifests`; raw en afgeleide tabellen staan buiten Git.
- Deze review controleerde software en dataproeven; providerprijzen zijn niet opnieuw geverifieerd.
