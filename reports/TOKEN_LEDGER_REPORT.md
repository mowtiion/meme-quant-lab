# Token instruction and fee audit — 2026-09-24

## Result and scope
The next ledger layer is implemented and tested against the existing verified Alchemy sample.
**This is partial coverage, not a complete SOL/token/supply ledger.** Every unsupported case is
reported; no comparison tolerance, balance adjustment or guessed missing state was introduced.

Input: 41 verified blocks, artifact 10819402938, SHA-256
`bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
All evidence is verified offline before auditing; new chain requests: **0**.
Machine-readable checkpoint: `TOKEN_LEDGER_VERIFICATION.json`.

## Account-flow results
Population: all 2,873 successful transactions invoking Pump or PumpSwap through top-level or
inner instructions, including invocations with no decoded trade event. The 1,085 failed target
transactions are counted separately and excluded from committed token-state reconstruction.

| Observation | Count |
|---|---:|
| Transactions with every inspected token account reconciled | 477 |
| Transactions with partial account coverage | 2,360 |
| Transactions held back for account reinitialization | 36 |
| Reconciled account observations | 17,186 |
| Unresolved account observations in parsed transactions | 2,585 |
| Decoded transfer / burn / mint instructions | 12,963 / 5 / 8 |

Account observations are per transaction, not unique wallets. The 36 unparsed lifecycle cases
are not included in the account observation denominator. Instruction counts describe parsed
operations, including transactions with partial coverage; they are not a claim that all supply
changes have been independently reconciled against mint-account state.

Of the 2,585 unresolved account observations, 2,522 require a lamport ledger for wrapped-SOL
initialization/sync/closure. The other 63 occur in transactions containing unsupported token
instructions. Observed unsupported first-byte tags: 26 (3), 39 (5), 210 (5), 215 (5), 45 (1).
These are raw first-byte classifications, not a claim that every instruction follows the
one-byte TokenInstruction enum (metadata interfaces can use wider discriminators).

## Fee and protocol-burn results
| Check | Count |
|---|---:|
| AMM actions with core transfers and protocol/creator fee destinations reconciled | 2,110 |
| Protocol buy-and-burn actions reconciled separately | 3 |
| Transaction groups requiring multi-event fee attribution | 256 |
| Nonzero cashback/holder-reward or incomplete fee variants held back | 31 |
| Fee check held back for unsupported token instruction | 1 |

Fee matching is restricted to token calls beneath the identified AMM invocation using CPI
stack depth; unrelated sibling transfers cannot satisfy the check. For the supported zero
cashback/holder-reward cases, protocol recipient receives protocol_fee minus buyback_fee;
creator transfer matches coin_creator_fee and the pinned instruction's creator vault. Main
base and quote transfers must also match. Remaining quote transfers sum exactly to buyback_fee,
but their recipient identities are **not** asserted to be official buyback destinations.
This is an observed sample reconciliation, not independent validation of the pricing/fee formula.

The three protocol burns recheck the existing instruction/event/companion and exact balance
reconciliation, plus the explicit SPL Burn instruction. They remain excluded from wallet demand.

## Implementation and fail-closed behavior
- `src/meme_quant/token_ledger.py`: compiled transfer/checked-transfer, mint/checked-mint,
  burn/checked-burn decoding; exact per-account net deltas; program/mint/decimal consistency.
- `src/meme_quant/fee_audit.py`: narrow instruction-scoped fee reconciliation and protocol-burn check.
- Missing metadata, conflicting identities, malformed binary data, duplicate balance rows,
  duplicate inner groups and caught CPI failures do not pass. Unknown token extensions block
  full token-account reconciliation for that transaction.
- Missing boundary amount can be zero only for an explicitly initialized or closed non-native
  account. Native wrap/sync/close and repeated initialization remain unresolved.
- This net-flow audit does not prove intermediate liquidity, full account lifetime ordering,
  transfer-fee withheld extension balances, mint supply snapshots or cross-transaction continuity.

19 new tests cover exact conservation, one-unit corruption, wrong decimals/program/recipient,
new and closed accounts, native lifecycle gaps, unknown extensions, inner failures, duplicate
metadata, binary truncation, real protocol/creator/buyback splitting, sibling CPI attribution,
missing depth and unsupported fee variants. The real test fixture is traced to slot 449382002,
transaction index 10 and the original primary object hash.

## Reproduce
```
PYTHONPATH=src python scripts/audit_token_ledger.py ARTIFACT.zip --summary-only --out SUMMARY.json
PYTHONPATH=src python scripts/audit_token_ledger.py ARTIFACT.zip --out FULL_DETAILS.json
PYTHONPATH=src python -m unittest discover -s tests -p test_token_ledger.py
PYTHONPATH=src python -m unittest discover -s tests -p test_fee_audit.py
```
Per-slot hashes and the full-detail digest allow results to be checked after a reset.

## Next bounded work
Prioritize a SOL/lamport and account-lifecycle ledger: this addresses the largest explicit gap.
Then handle multi-action fee attribution and cashback/holder/extension variants. Verify buyback
recipient provenance rather than guessing from residual amounts. Keep the full ledger gate and
EXP-000 blocked until these requirements and the existing historical-data gates are satisfied.

## Protocol references consulted
- SPL Token 9.0.0 instruction definitions: https://docs.rs/spl-token/9.0.0/spl_token/instruction/enum.TokenInstruction.html
- Token-2022 interface 3.1.1 definitions and binary packing:
  https://docs.rs/spl-token-2022-interface/3.1.1/src/spl_token_2022_interface/instruction.rs.html
- PumpSwap instruction and event accounts/fields: the repository's pinned `vendor/pump_amm.json`.

The crate references explain the instruction formats. They do not independently certify the
historical deployed binaries; that existing research gate remains open.
