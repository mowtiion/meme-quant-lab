# SOL cash-flow and wrapped-SOL lifecycle audit — 2026-09-24

## Result

The instruction cash-flow model matches every account's exact post-lamport balance in
**2,607 of 2,873 successful Pump/PumpSwap-invoking transactions (90.74%)**.
The 1,085 failed target transactions are excluded, not counted as passed.
This is a scoped cash-flow reconciliation, not completion of the economic ledger or EXP-000.

| Check | Result |
| --- | ---: |
| Transactions with all modeled post-lamports matching | 2,607 |
| Transactions with unexplained post-state residuals | 234 |
| Transactions with a modeled intermediate funds deficit | 23 |
| Transactions stopped by unsupported token instructions | 9 |
| Native account observations in passed transactions | 8,197 |
| Reused account observations in passed transactions | 32 |
| WSOL initializations in passed transactions | 2,510 |
| SyncNative calls in passed transactions | 1,704 |
| WSOL closures in passed transactions | 2,520 |
| New blockchain requests | 0 |

Counts of account observations include repeated addresses across transactions. They are not
distinct wallets. The 9 unsupported transactions use tags 26 (3), 39 (5), and 45 (1).

## What was checked

`src/meme_quant/lamport_ledger.py` starts from raw `preBalances`, debits the fee payer once,
and replays compiled top-level and inner instructions once, in execution order. It models
System creation, transfers, seeded creation/transfers and nonce withdrawals; native-token
transfers move equal integer lamports. Account closure sends the entire currently modeled
lamport balance to its named destination. Initialization, closure and reinitialization are
tracked as separate account lifetimes. SyncNative is recorded without inventing a second
cash transfer. All account end balances and total lamport conservation are checked.

No historical rent constant is assumed. The separate token amount computed by SyncNative
depends on the account's stored native reserve, which this audit does not independently read.
Therefore `sync_token_amounts_independently_verified` remains false. Previous token-ledger
gaps are not relabeled as passed merely because SOL cash flow matches.

Only successful transactions with usable logs enter replay. Unknown token/System variants,
invalid identities or indexes, duplicate inner groups, failed inner execution and intermediate
funding deficits remain explicit failures. Arbitrary other programs can mutate owned account
lamports directly. Such movements are not yet modeled: unmatched net effects remain residuals;
offsetting direct movements can be invisible to endpoint comparison. Consequently a pass
proves that this modeled sequence matches the boundaries, not independent completeness of
all gross internal economic flows or historical binary semantics.

## Unresolved evidence and next work

Residuals are retained per account with predicted/observed balances. Across the 234 residual
transactions, 96 have two affected accounts, with other cases ranging up to 24 accounts.
The repeated amount 1,346,200 is diagnostic only; it is not treated as a rent constant.

At slot 449382000, transaction 837, a System transfer at position `[3, 9]` requests
1,062,597,817 lamports while the modeled source balance is only 47,565,731. The preceding
execution includes a Pump Sell. This makes direct program cash flows a concrete next target,
but does not by itself establish the missing amount's full provenance. The transaction remains
unresolved. Do not infer missing movements from the answer needed to match `postBalances`.

Next: model direct program transfers/refunds from validated program semantics and attributed
events; support the identified extension variants; obtain historical stored reserve evidence
for native token amounts. Multi-action fee attribution, cashback/holder variants, official
buyback recipient provenance and cross-transaction continuity remain separate open work.

## Reproduction and tests

Input: the already verified 41-block artifact, slots 449382000–449382040, artifact ID
10819402938, from successful GitHub Actions run 36025502200.
Artifact SHA-256: `bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
The runner checks the artifact and frozen raw/reference hashes before replay.
Full detail digest: `7c9c22c0550c1b84c0ad418453d950b6151a40c89d5933d719c8d606139d9f33`.
Per-slot digests, counts and representative exceptions are in
[`LAMPORT_LEDGER_VERIFICATION.json`](LAMPORT_LEDGER_VERIFICATION.json).

```bash
PYTHONPATH=src python scripts/audit_lamport_ledger.py alchemy41-evidence.zip --out lamport-full.json
PYTHONPATH=src python scripts/audit_lamport_ledger.py alchemy41-evidence.zip --out lamport-summary.json --summary-only
python -m unittest discover -s tests -v
```

13 new tests cover wrap/transfer/close, reuse, SyncNative non-double-counting, exact fee handling,
one-lamport tampering, residual preservation, malformed/unknown variants, use after closure,
negative indexes, missing boundaries, inner failures, intermediate deficits, seeded layouts
and nested execution. A real transaction fixture from slot 449382000, index 95, exercises
two account lifetimes and returns 1,488,440 then 13,853,114,874 lamports at closure. Fixture
provenance includes the source artifact and raw block response hashes. All **179** local
tests pass with the project's pinned dependencies.

## Semantic references and limits

- [SystemInstruction layouts](https://docs.rs/solana-system-interface/3.3.0/solana_system_interface/instruction/enum.SystemInstruction.html)
- [SPL Token processor, CloseAccount and SyncNative](https://docs.rs/spl-token/9.0.0/src/spl_token/processor.rs.html)

These published interfaces guide the modeled instruction behavior. They do not independently
prove the deployed program binaries at the historical slots; that mapping remains an open gate.
