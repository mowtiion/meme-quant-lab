# Resume checkpoint — 2026-09-24

## Goal
Complete the second-source 41-block validation, then proceed with EXP-000 research gates.
No paid subscription, wallet operations or bulk history download is authorized/needed here.

## Completed
- Alchemy app Solana Mainnet enabled with explicit user approval. HTTP 403 resolved.
- Actions run 36022303474 attempt 2 fetched two full blocks (artifact 10818382262).
- Slot 449382002 is exact; 449382004 differs only in seven numeric uiAmount fields.
- Both blocks now pass offline comparison under an explicit one-ULP policy.
- Exact amounts, decimals, uiAmountString, null and all other fields are retained.
- All original hashes of 41 primary blocks verified before generating canonical hashes.
- Never remove log/balance fields or apply a broad floating-point tolerance.

## Next operation already prepared
Merge the token-ui-and-alchemy41 change after Integrity tests pass. This changes
`configs/alchemy_phase_b_request.json`, which triggers one bounded main-branch workflow.
No browser login or manual user click is required. Limits: 42 calls, 192 MiB, 600 seconds;
no automatic retries. Workflow only triggers on that explicit request file or manual dispatch.
Ordinary code/report updates do not download anything.

Workflow: `.github/workflows/alchemy-phase-b.yml`.
On failure, inspect comparison.json and preserve completed raw evidence; do not blindly rerun.
On success, download the `alchemy-phase-b-evidence` artifact and independently rehash with:

```
python scripts/verify_alchemy_phase_b.py ARTIFACT.zip --out reports/ALCHEMY_PHASE_B_VERIFICATION.json
```

Artifact retention is 30 days. Raw blocks remain outside Git; comparison hashes and decisions
belong in reports. Update this checkpoint with the run ID and verification outcome.

## Remaining research gates (not solved by a 41-block match)
Upstream independence, full creation census, binary/IDL deployment mapping, historical
pool/reserve and transfer ledgers, and bounded 1,000-launch backfill planning.
EXP-000 stays FAIL/BLOCKED until those gates are demonstrated. See docs/NEXT_STEPS.md.
