# Meme Quant Lab — EXP-000

Onderzoek of vroege on-chain signalen toekomstige Solana/Pump.fun-runners kunnen rangschikken.
**Research only. EXP-000 is nog niet geslaagd. Er is geen aangetoonde trading-edge.**

## Wat er staat

- Begrensde, read-only Solana-RPC collector; finalized blocks inclusief transactieversie 1.
- Ongewijzigde raw JSON-responses op SHA-256-adres, plus herleidbare manifests.
- Vastgelegde Pump/PumpSwap-IDL's; decoder met programma-attributie en expliciete fouten.
- Pump/PumpSwap-handelsnormalisatie en snapshots op 10/30/60/120/300 seconden.
- Sampling uit een launch-census, inclusief launches zonder trades.
- Handelsstromen, buyer/trade/volume-dynamiek en conditionele prijs/curve-afgeleiden.
- Gescheiden diagnostische outcomes; onuitvoerbare prijzen worden geen winstlabels.
- Parquet-tabellen, DuckDB-database, reproduceerbare configuratie en runrapporten.
- 75 tests voor tijdsgrenzen, look-ahead, ontbrekende data, duplicates, censoring, echte transacties en opslag.
- Protocol buy-and-burn-acties apart gereconcilieerd; ze tellen niet als walletkopers of gewone koopdruk.

## Starten — Python 3.12

Voer commando's vanuit deze projectmap uit. Er is geen wallet of API-key nodig voor de offline tests.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m unittest discover -s tests -v
python -m meme_quant.cli smoke --out data/processed/synthetic-new
```

De smoke-run selecteert 1.000 **synthetische** launches uit een kunstmatige census van 1.200.
Dit test de software; het vervangt nooit de gevraagde 1.000 echte launches.

```bash
python -m meme_quant.cli collect --start-slot 449382001 --end-slot 449382008 --max-slots 8
python -m meme_quant.cli replay --manifest data/raw/manifests/RETURNED_HASH.json --out data/processed/real-new
```

Gebruik het werkelijk teruggegeven manifestpad. Downloads zijn expliciet begrensd.
Nieuwe runs krijgen een nieuwe outputmap; bestaande raw bestanden worden niet overschreven.
Een eigen read-only RPC kan via `SOLANA_RPC_URL`; `.env` wordt niet automatisch geladen.
Kies geen betaald endpoint voordat het gebruik en budget zijn goedgekeurd.

## Grenzen van versie 0.1

AMM-trades worden gekoppeld via de eigen instructies en tokenbalansmetadata; onopgeloste gevallen
gaan naar de foutenlijst. Er is nog geen complete historische pool/reserve-ledger.
Holder-, transfer-, creator- en walletgeschiedenis ontbreken. Historische IDL-upgrades zijn niet
aan deployment-slots gekoppeld. Live aankomsttijden zijn niet uit historische downloads afleidbaar.
Raw blokcompleetheid is geen bewijs van een complete launch-census of correcte economische boekhouding.

Daarom blijven de onderzoeksgates dicht, ook bij een foutloze smoke-run. De code bevat geen
ML-training, wallet-signing, live trading of verborgen betaalde integraties.

De herhaalde 41-blokkenproef bevat 3.082 events zonder decodeer-/normalisatiefouten.
CPI-herstel voegt in de archiefproef één ontbrekend koop-event toe, zonder dubbeltelling.
Die proef bevat nu 168 events en één onbevestigd administratief event. De volledige
reconstructie van 1.000 echte launches blijft geblokkeerd. Het pilotplan staat in `configs/pilot1000.json`.

```bash
python -m meme_quant.cli preflight --report experiments/exp000/archive-preflight-v3.json
```

Deze controle geeft exitcode 2 zolang de onderzoeksvoorwaarden niet zijn gehaald.

Zie [het CPI-herstelrapport](reports/CPI_RECOVERY_REPORT.md), [het onderzoeksrapport](reports/EXP000_REPORT.md), [databronnen](docs/DATA_SOURCES.md),
[schema's](docs/SCHEMAS.md) en [het vervolgplan](docs/NEXT_STEPS.md).

De officiële repository staat op [github.com/mowtiion/meme-quant-lab](https://github.com/mowtiion/meme-quant-lab).
Grote raw datasets en gegenereerde tabellen blijven buiten GitHub; code, schema's, tests en rapporten staan daar wel.
