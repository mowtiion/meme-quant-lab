# Integriteitstests — 23 september 2026

120 tests geslaagd, 0 mislukt, lokaal en op GitHub Actions.

20 aanvullende controles dekken bytecoverage, overschrijvingen, autoriteit, account-hergebruik,
onvolledige bufferhistorie, ongeldige hashes, stortingen zonder datawijziging en afgebroken
of langzaam binnenkomende HTTP-responses. De echte reconstructie matcht alle 1.623
historietransacties en alle 1.638.312 programmabytes.
Zie `reports/HISTORICAL_BINARY_VERIFICATION.json` en
[de CI-run](https://github.com/mowtiion/meme-quant-lab/actions/runs/35825899874).

25 eerdere controles dekken censusreconciliatie, ontbrekende/dubbele/afwijkende creates,
EOF-argumenten, tuple-structs, holder-rewards-PDA, overlappende manifests, expliciet gesloten
onderzoeksgates, loader-metadata en twee echte historische upgrade-instructies.
Zie `reports/CENSUS_REGIME_VERIFICATION.json`.

21 nieuwe CPI-hersteltests controleren de twee afgebroken transacties, vier volledige
transacties met gesimuleerde ontbrekende logs, deduplicatie, instructievolgorde,
programma/autoriteit, beschadigde metadata, payloadtegenspraak en teruggedraaide/onbewezen
uitvoering. De nieuwe replays zijn inhoudelijk vergeleken tussen JSONL, Parquet en DuckDB.
Zie `reports/CPI_RECOVERY_VERIFICATION.json`.

```bash
python -m pip install -r requirements.lock
PYTHONPATH=src python -m unittest discover -s tests -v
```

De 14 controles uit de voorafgaande review omvatten drie echte protocoltransacties, foutieve/missende bewijsstukken,
protocolkopers versus wallets, teruggedraaide CPI-events, finalized-provenance, de minimale 1.000
launches en behoud van grote raw-integers in zelfstandige Parquet/DuckDB-exports.

In de voorafgaande review zijn drie datasets opnieuw gegenereerd: zes tabellen per run hebben gelijke
JSONL/Parquet/DuckDB-aantallen. De databases vereisen geen WAL-bestand.
Alle 52 raw-objecten en de twee vastgelegde IDL's zijn op hash gecontroleerd.

[CI op de broncode van deze runs](https://github.com/mowtiion/meme-quant-lab/actions/runs/35778400374).
Dit bewijst softwaregedrag, geen volledige historische dekking of trading-edge.
