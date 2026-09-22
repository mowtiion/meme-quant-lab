# Integriteitstests — 22 september 2026

54 tests geslaagd, 0 mislukt, lokaal en op GitHub Actions.

```bash
python -m pip install -r requirements.lock
PYTHONPATH=src python -m unittest discover -s tests -v
```

De 14 nieuwe controles omvatten drie echte protocoltransacties, foutieve/missende bewijsstukken,
protocolkopers versus wallets, teruggedraaide CPI-events, finalized-provenance, de minimale 1.000
launches en behoud van grote raw-integers in zelfstandige Parquet/DuckDB-exports.

Daarnaast zijn drie datasets opnieuw gegenereerd: zes tabellen per run hebben gelijke
JSONL/Parquet/DuckDB-aantallen. De databases vereisen geen WAL-bestand.
Alle 52 raw-objecten en de twee vastgelegde IDL's zijn op hash gecontroleerd.

[CI op de broncode van deze runs](https://github.com/mowtiion/meme-quant-lab/actions/runs/35738444376).
Dit bewijst softwaregedrag, geen volledige historische dekking of trading-edge.
