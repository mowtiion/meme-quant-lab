# Transaction-bounded PumpSwap reserve ledger — 2026-09-24

## Result
**PASS for ordinary PumpSwap vault-flow replay in the verified 41-block sample.**

| Observation | Count |
|---|---:|
| Reconciled transaction/pool groups | 2,404 |
| Reconciled ordinary buy/sell events | 2,663 |
| Distinct reconciled pools | 187 |
| Groups with multiple sequential trade events | 250 |
| Protocol buy-and-burn groups kept separate | 3 |
| Other unresolved groups | 0 |
| Decoder issues | 0 |
| New network requests | 0 |

Input: verified Alchemy artifact 10819402938, SHA-256
`bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
The audit independently verifies all 41 raw block comparisons before reading their events.
Machine-readable summary, per-slot ledger hashes and examples: `RESERVE_LEDGER_VERIFICATION.json`.
The full detail digest is recorded; full rows can be regenerated offline with the script below.

## What is actually checked
Resolve pool base/quote vault addresses and mint identities from the pinned PumpSwap
instruction layout, including loaded addresses. Require unambiguous instruction attribution
and matching counts of ordinary buy/sell instructions and events for each participant identity.
Require both pre- and post-token balance rows with identical decimals and mint identity.

Start from the transaction's exact integer pre-balances. Each event's stated pre-reserves
must match the running ledger. For buys, subtract base_amount_out and add
quote_amount_in_with_lp_fee. For sells, add base_amount_in and subtract
quote_amount_out_without_lp_fee. Replay multiple events in log order. Require resulting
vault balances to equal the actual integer post-balances exactly. No uiAmount floats,
price tolerances, guessed zero balances or inferred missing events are used.

This demonstrates these event fields' reserve-flow interpretation on this sample, including
buy_exact_quote_in instructions. It does not independently prove the pricing/fee formula.
Tests cover correct integer flow, multi-action order, incorrect post-state, duplicate events,
missing balances, incomplete/failed execution, protocol-burn separation, mint/decimal changes,
and one-unit differences above floating-point precision (2**60).

## Explicit limits and next action
This is a transaction-bounded vault ledger. It does **not** yet establish continuity between
transactions/blocks, all recipient fee flows, Token-2022 transfer-fee accounting, transfer/mint/burn
supply conservation, historical pool creation/state validity, executable prices or profit labels.
The three protocol burns already have separate decoder reconciliation; they are deliberately
not classified as ordinary buyer demand or silently counted as passing this ordinary-flow gate.

Next: add instruction-level SPL Token/Token-2022 transfer, mint and burn accounting, reconcile
protocol/creator/holder fee recipients, and prove pool-state continuity on the same sample.
Keep unsupported variants explicitly unresolved. EXP-000 remains blocked until all required gates pass.

## Reproduce without RPC
```
PYTHONPATH=src python scripts/audit_reserve_ledger.py ARTIFACT.zip --summary-only --out SUMMARY.json
PYTHONPATH=src python scripts/audit_reserve_ledger.py ARTIFACT.zip --out FULL_LEDGER.json
PYTHONPATH=src python -m unittest discover -s tests -p test_reserve_ledger.py
```
