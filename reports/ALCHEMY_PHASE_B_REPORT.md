# Alchemy phase B — verified, 2026-09-24

## Decision
**PASS for the frozen 41-block second-source comparison.** This resolves the provider
access and numeric representation blockers. No new provider or rerun is needed for this range.
It does not establish full historical coverage, independent upstream infrastructure, an
independent decoder, or a trading edge. EXP-000 remains blocked on separate research gates.

## Evidence
- Run: https://github.com/mowtiion/meme-quant-lab/actions/runs/36025502200
- Code commit: `acb788c15b45216242946f97aad584a011b7dbfd` (PR #6).
- Artifact: `10819402938`, `alchemy-phase-b-evidence`, expires 2026-10-24.
- ZIP SHA-256: `bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
- Slots: 449382000–449382040 inclusive; enumeration matches all 41 frozen slots.
- 42 requests, 140,090,905 raw response bytes; limits 42 requests / 192 MiB / 600 seconds.
- Workflow passed. Downloaded evidence was separately rehashed and recomputed offline.
- Machine-readable evidence: `ALCHEMY_PHASE_B_VERIFICATION.json` and `ALCHEMY_EVENT_VERIFICATION.json`.

## Comparison result
| Check | Result |
|---|---:|
| Blocks verified | 41/41 |
| Transactions | 43,417 |
| Blocks with exact field-group hashes | 19 |
| Blocks matching the explicit canonical UI rule | 22 |
| Decoded Pump/PumpSwap events, identical between datasets | 3,258 |
| Normalized events, identical between datasets | 3,082 |
| Decode / normalization issues | 0 / 0 |
| Trades | 3,072 |
| Protocol buy-and-burn actions | 3 |
| Creates / completion / migration | 5 / 1 / 1 |

All logs are checked in full; no log truncation exception was added. The five creates
are independently retrieved observations within this window, not a complete historical census.
The same pinned decoder was run on both datasets, so this is not independent parser validation.

## Exact rule, not a weakened balance check
For redundant numeric `uiAmount`, derive a binary64 value from the exact integer `amount`
and `decimals`. Only accept an input within one binary64 ULP of that value, and verify
`uiAmountString` equals the exact decimal amount. Preserve and compare `amount`, `decimals`,
`uiAmountString`, null, owners, mints, all other metadata and every transaction field.
The previously audited pre-execution empty-array/null rule remains narrowly scoped.
Original raw responses and exact hashes remain unchanged; exact and canonical outcomes
are reported separately. Changed exact amounts and truncated logs still fail regression tests.

Canonical reference hashes were rebuilt from the original 41 primary objects only after
checking every original SHA-256 and all original field-group hashes. Reproduce with
`scripts/build_second_source_canonical_reference.py` when those primary objects are available.

## Reproduce without another API call
```
python scripts/verify_alchemy_phase_b.py ARTIFACT.zip --out VERIFIED.json
PYTHONPATH=src python scripts/audit_alchemy_events.py ARTIFACT.zip --out EVENTS.json
```
The event audit additionally requires original primary raw objects and pinned vendor IDLs.

## Next research work
Proceed with a small, offline pool/reserve and transfer/mint/burn ledger on this verified
sample. Keep protocol buy-and-burn separate from wallet demand. Establish upstream provenance
and historical IDL validity, then estimate bounded full-census costs before bulk collection.
Do not repeat setup, switch providers or redownload these 41 blocks to solve unrelated gates.
