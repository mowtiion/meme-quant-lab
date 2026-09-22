# Integriteitstests — 22 september 2026

75 tests geslaagd, 0 mislukt, lokaal en op GitHub Actions.

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

[CI op de broncode van deze runs](https://github.com/mowtiion/meme-quant-lab/actions/runs/35776709066).
Dit bewijst softwaregedrag, geen volledige historische dekking of trading-edge.
