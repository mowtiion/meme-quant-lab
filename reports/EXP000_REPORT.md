# Meme Quant Lab — EXP-000

Datum: 22 september 2026. **Onderzoeksgate: FAIL — EXP-001 blijft geblokkeerd.**

De eerste engineeringversie werkt en is getest. De gevraagde reconstructie van 1.000 echte,
willekeurig gekozen launches is **nog niet uitgevoerd**. Er is geen bewijs voor een trading-edge.

## Uitgevoerd

| Onderdeel | Resultaat |
|---|---|
| Integriteitstests | 40 geslaagd, 0 mislukt; inclusief echte Pump- en PumpSwap-transacties |
| Echte dataproef | 41 opeenvolgende finalized blocks, slots 449382000–449382040 |
| Genormaliseerde events | 3.079: 3.072 trades, 5 creates, 1 curve-completion, 1 migratie |
| Echte launchsteekproef | Alle 5 aangetroffen launches; geen selectie op koersresultaat |
| Echte snapshots/outcomes | 25 / 125 diagnostische rijen; allemaal onvoldoende gevalideerd |
| Quarantaine | 3 events met onopgeloste PumpSwap-accountidentiteit |
| Synthetische softwaretest | 1.000 gekozen uit 1.200 kunstmatige launches; 5.000 snapshots, 25.000 outcomes |
| Opslagcontrole | Parquet en DuckDB-aantallen komen overeen met de runrapporten |
| Uitgaven / live trading | Geen betaald dataproduct aangeschaft; geen wallet of live trade gebruikt |

De ruwe bloktijden lopen van **2026-09-22T12:42:04+00:00** tot **2026-09-22T12:42:15+00:00**. Dit is een korte innameproef,
geen representatieve historische onderzoeksperiode. De raw-responses beslaan circa 133.6 MiB.
De publieke RPC leverde de geselecteerde blokken; dit bewijst geen onbeperkte archiefcapaciteit.

## Wat aantoonbaar werkt

De pipeline bewaart oorspronkelijke bytes en SHA-256-hashes, controleert de slotenumeratie,
decodeert events aan de hand van vastgelegde IDL's en gebruikt transacties van versie 1.
Ze bewaakt cutoff-tijden, geslaagde/finalized transacties, identieke en conflicterende duplicates,
onbekende decimals, quote-units, vertraagde ontvangst en gecensureerde outcomes.

De softwaretest controleert alleen de programmatuur. Haar 1.000 launches tellen niet mee als
empirische validatie. De gate wordt ook bij deze succesvolle test niet vrijgegeven.

## Data-integriteit per familie

| Familie | Gate | Reden |
|---|---|---|
| Token/market/curve | FAIL | Historische regimes en reserveboekhouding niet onafhankelijk gereconcilieerd |
| Trading | FAIL | Drie onopgeloste AMM-events; geen onafhankelijk bewijs van volledige economische dekking |
| Dynamics | FAIL | Berekeningen getest, maar echte snapshotvensters niet compleet |
| Holders/distributie | FAIL | Historische transfers, account-eigenaars en volledige balances ontbreken |
| Creator/wallet/graphs | FAIL | Historie en point-in-time reputaties nog niet opgebouwd |
| Outcomes | FAIL | Onvoldoende vervolgdata en geen gevalideerde uitvoerbare entryreference |
| Launchpopulatie | FAIL | Slechts vijf launches; onafhankelijke volledige census nog niet gecontroleerd |

De drie onopgeloste events staan op slots **449382008, 449382021 en 449382027**. De parser kan
hun accountverwijzing `11111111111111111111111111111111` niet betrouwbaar aan een token koppelen.
Ze staan met signatures in `issues.jsonl`; hun betekenis is niet geraden of stilzwijgend weggefilterd.

Voorbeelden: `2mhjbvEJ9d4TCnHRxeRfkaRxoSBdFtrFVXEg3uScpump` en
`FAUM2TEWzbxBPjFvPp6qvqft7Tgh2D6fnhLoJF4Mpump` worden als creates behouden.
Hun vervolgvensters zijn niet volledig gedekt. Van de 125 outcome-rijen zijn 40 CENSORED en 85
UNPRICED. Dat zijn geen negatieve runnerlabels. Alle uitvoerbare returnlabels blijven NULL.

## Eerstvolgende stap

Los de drie eventvarianten op tegen de officiële instructiedefinities; valideer de historische
parser- en regimedekking. Verkrijg daarna een complete creatie-census plus trades/transfers en
voldoende follow-up voor een vooraf vastgelegde pilotperiode. Pas dan willekeurig 1.000 echte
launches trekken en alle vijf snapshotmomenten reconstrueren.

De bronvergelijking staat in `docs/DATA_SOURCES.md`. Direct RPC, Helius en Bitquery zijn onderzocht.
Historische candles alleen voldoen niet. Totale backfillkosten zijn nog onbekend; actuele
accountrechten, retentie en een begrensde proef moeten eerst bevestigd worden. Geen abonnement
of bulkdownload goedgekeurd of aangeschaft.

## Reproduceerbaarheid

- Codecommit bij beide runs: `2b649a011551e726924d26315df1810d558ae66d`; working tree was schoon.
- Echte datasetversie: `f8bc8095d4d00e53479866937db9ccb1381e788e8db929d4c8576910d05ed3f5`.
- Synthetische datasetversie: `ec34a96330ec4c16013e83563fff45786604c10230457c3f6a35f4380aeada39`.
- Real manifest: `data/raw/manifests/e6f27b744a0dcd838d24de1b916109ac8cd744cdf2103871bc2592d0f90413b5.json`.
- Testcommando: `python -m unittest discover -s tests -v` met `PYTHONPATH=src`.
- Python 3.12.14; PyArrow 25.0.1; DuckDB 1.5.5; dependencybestand inbegrepen.
- Volledige raw bytes, manifests, runconfiguraties, outputtabellen, bronverwijzingen en lokale
  Git-historie zitten in het projectarchief. Er is nog geen GitHub-remote gekoppeld.

Officiële referenties: [Pump](https://github.com/pump-fun/pump-public-docs),
[Solana-tijdsdefinitie](https://solana.com/docs/rpc/http/getblocktime),
[Bitquery-retentie](https://docs.bitquery.io/docs/graphql/data-coverage-retention/),
[Helius-history](https://www.helius.dev/docs/rpc/gettransactionsforaddress).
