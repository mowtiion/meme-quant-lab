# Economic checkpoint — 2026-09-24

## Decision

**The ordinary PumpSwap instruction fee audit is complete for this frozen sample.**
All 2,663 ordinary AMM trade events pass, plus the 3 separately classified protocol burns.
This closes the previous multi-event fee-attribution and observed cashback/holder-variant gaps.
**EXP-000 and the 1,000-launch historical pilot remain blocked.** No collection or trading gate
has been relaxed. The next work is historical state and the remaining direct program flows.

## Measured results

Same hash-verified input: 41 blocks, slots 449382000–449382040, 2,873 successful target
transactions. Another 1,085 failed target transactions are excluded, not passed. Zero new
blockchain requests; documentation and GitHub publication use separate network access.

| Check | Previous checkpoint | Current checkpoint |
| --- | ---: | ---: |
| All modeled SOL account end balances match | 2,607 transactions | 2,786 transactions |
| SOL transactions still unresolved | 266 | 87 |
| Ordinary AMM core fee checks passed | 2,110 | 2,663 |
| Multi-event fee transactions separately scoped | 0 | 256 |
| Passed cashback / holder-reward fee events | 0 / 0 | 2 / 30 |
| Ordinary token-account observations reconciled | 17,186 | 17,240 |
| Automated tests | 179 | 194 |

The fee comparison changes from a transaction-level hold to one result per event for multi-action
transactions; it is not a like-for-like subtraction of unresolved event counts. Every ordinary
AMM event now has its own result. The protocol burns never count as ordinary wallet demand.

Among SOL-passed transactions, 5,963 surviving native-token account observations also have
exact token balances reconstructed from known initial amounts and instruction deltas.
18 surviving observations still require stored-reserve evidence. This count excludes closed
accounts and is not a claim that all initialized/closed WSOL token lifetimes were verified.
It overlaps the ordinary token ledger; do not add the two account counts together.

## What changed

- Events are matched to their actual instruction through complete execution logs and CPI
  ancestry. The event's payload is checked against the raw log again. Repeated trades in
  the same pool use distinct instruction scopes; siblings cannot satisfy each other's fees.
- Direct native Pump sell payouts are modeled from event amounts and named instruction
  accounts. Native legacy/v2 sells are distinguished from token-quoted sells. No movement
  amount is fitted to the residual needed to match the final balance.
- Volume-account closure returns the live modeled account balance. Passed transactions
  include 87 such closures, 162 Pump sells, one cashback claim and one unwrap operation.
  The new direct movements run after the instruction's subtree, before later instructions.
- Holder rewards alias the reported creator fee and are not counted twice. Cashback goes
  to the derived user-volume-accumulator ATA. Buyback transfers must reach a unique adjacent
  documented recipient/derived quote-ATA pair in the instruction's remaining accounts.
  Pair identification tolerates following extension accounts; ambiguous pairs fail.
- Recipient/ATA identity and membership in the pinned documentation snapshot are checked.
  Historical Global configuration and the historical deployed binary remain unverified.
- Zero-fee TransferCheckedWithFee, metadata-pointer initialization, token-metadata initialization
  and metadata-authority changes have narrow binary decoders. Nonzero withheld transfer fees
  remain unsupported. Other extension variants are not silently ignored.
- Unwrap-all uses the tracked native token amount, not all lamports or an invented rent amount.
  The source remains open. New account initialization and SyncNative invalidate token-amount
  certainty when their stored reserve is absent; such amounts are never guessed.

Unknown token instructions outside an AMM instruction's subtree no longer block that AMM's
fee-only check. They still block the relevant whole-account token ledger. In the real unwrap
case, the AMM sell fee is proved while the old aggregate token parser still reports tag 45.

## The 87 remaining SOL cases

| Remaining class | Transactions | Next evidence needed |
| --- | ---: | --- |
| Net post-state residuals | 82 | Attribute direct mutations by the invoked programs; independently derive amounts and recipients |
| Additional sell-account layouts | 4 | Validate fee-sharing / remaining-account semantics before modeling those payouts |
| Intermediate funding deficit | 1 | Reconstruct native funding in the migration path before its account creation |

Every case is indexed by slot, transaction index and signature in
[`ECONOMIC_LEDGER_VERIFICATION.json`](ECONOMIC_LEDGER_VERIFICATION.json), including account
residuals or the blocked movement. 67 of the 87 cases invoke
`FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9`. This is a co-occurrence count, **not proof**
that this program causes all those residuals. Pump/PumpSwap and other program calls can coexist.

Do not discard these transactions from the research population, invent movements to force a
match, or treat a provider rerun as the remedy. The raw block evidence is already consistent.

## Gate before the historical pilot

1. Resolve the four fee-sharing sell layouts, migration funding and remaining direct program
   flows. Keep whole-transaction gaps separate from already-proved scoped trade fees.
2. Obtain historical native-account bytes or equally strong execution-state evidence for
   stored reserves where initialization/SyncNative token amounts remain unknown. Current
   account state is not a historical snapshot. Validate closed/reused token lifetimes and
   cross-transaction continuity. The old token gate still holds 36 reused-account transactions
   and 2,524 WSOL observations; passing the SOL subcheck does not automatically clear it.
3. Map historical deployed binaries to the supported IDL/semantics, establish census
   completeness and record provider upstream independence.
4. Only then finalize the bounded census/pilot collection budget and run the frozen
   `configs/pilot1000.json` plan. No paid plan, wallet operation or bulk collection was started.

This is the next major checkpoint: scoped AMM fees are closed; the blockers have moved to
historical execution state and direct program accounting. Do not restart GitHub/provider setup.

## Reproduction and evidence

```bash
PYTHONPATH=src python scripts/audit_economic_ledger.py alchemy41-evidence.zip --out economic-full.json
PYTHONPATH=src python scripts/audit_economic_ledger.py alchemy41-evidence.zip --out economic-summary.json --summary-only
python -m unittest discover -s tests -v
```

Install the pinned dependencies first. The runner verifies every frozen reference/raw hash,
decodes the blocks afresh, then computes token, SOL and scoped fee checks together.

- Artifact ID: 10819402938 (run 36025502200; expiration 2026-10-24).
- Artifact SHA-256: `bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
- Full detail digest: `294f63100bf7b73e34a69752615f039013057bfe9e220bf3e581847b0ac69145`.
- The JSON report contains per-slot result digests and all unresolved SOL cases.
- Five real transaction fixtures retain raw block hashes and artifact provenance.
- 15 new tests cover real sells, closure, cashback, holder aliases, multi-action scoping,
  unwrap, unknown-scope instructions, payload/recipient/balance tampering and binary decoders.
  All 194 tests pass locally. Source references and immutable repository revisions are in
  [`ECONOMIC_SOURCES.json`](ECONOMIC_SOURCES.json).

An endpoint match still proves a modeled sequence matching boundaries, not completeness of
offsetting hidden direct movements, historical binary equivalence, or any profitable signal.
