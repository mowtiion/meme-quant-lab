# Historical token continuity and migration checkpoint — 2026-09-24

## Result and decision

The four additional native sell layouts and the migration funding case now reconcile.
**2,791 of 2,873 target transactions match all modeled SOL end balances**; the remaining
**82** have explicit net residuals. All **2,663** ordinary AMM fee checks and the three
separate protocol burns continue to pass. There are no longer unsupported-layout or
intermediate-funding exceptions in this sample's SOL replay.

A new, separate audit traversed **all 43,417 transactions** in the 41 verified blocks,
including **3,431 failed transactions** and transactions that never invoke Pump/PumpSwap.
It found **zero token boundary discontinuities, unknown boundaries or failed-transaction
token changes**. The block parent slots and hash chain also match throughout the sample.

| Boundary continuity measure | Count |
| --- | ---: |
| Distinct accounts observed in token boundaries | 10,047 |
| Matching next-pre / previous-post links | 44,046 |
| Links with token amounts and identities on both sides | 43,908 |
| Links with an absent account on both sides | 138 |
| Matching links crossing a slot boundary | 14,716 |
| Absent-before / token-after account boundaries | 1,094 |
| Token-before / absent-after account boundaries | 521 |

Account creation boundaries are **not token launches**. Accounts created and closed entirely
inside one transaction may never appear in the RPC token balance boundaries and are outside
this continuity count. This does not clear the separate 36 reused-account transaction holds
or the missing stored reserves in the aggregate token ledger.

**The pilot remains blocked.** Boundary continuity is now proved for this frozen sample;
unexplained intra-transaction economics, historical native reserves, historical binary/config
mapping, census completeness and provider upstream independence remain separate open gates.

## Four native sells

The extra account in each sell is the independently derived Pump PDA with seeds
`["bonding-curve-v2", mint]`. The checker accepts that specific trailing account in the
`sell_v2` layout and rejects any other extra account. The source event and instruction remain
bound through execution logs. The existing payout formulas reconcile all four transactions.

The first real fixture, slot 449382033 / transaction 502, carries a shareholder list but sends
its 2,998,776-lamport creator fee to the named creator vault. This change does **not** pretend
that this trade itself distributes the accrued fee to shareholders.

## Migration funding

At slot 449382020 / transaction 750, the migration event supplies two independently encoded
amounts: **15,000,001 lamports** for the migration expense budget and **84,990,359,056 lamports**
for pool quote funding. The native-only `migrate_v2` model routes the budget from the bonding
curve to the derived pool-authority PDA before child account creation, and the quote funding
to the authority's native-token account before its unique SyncNative and pool transfer.

The companion CreatePoolEvent must belong to a direct child `create_pool` call, match the
migration identities and amounts, and agree with the base/quote amounts encoded in the pool
instruction. Account names, pool-authority derivation, native quote, instruction lengths and
the unique sync location are checked. Replayed creates, transfers, closures and refunds then
match every observed end balance. No transfer amount is fitted from a post-state residual.

This is an event-constrained funding model. The placement of direct funding between program
calls is constrained by the dependent creates/sync, not a separately captured intra-instruction
account-state trace. Historical program-binary equivalence remains unproved. The observed
SyncNative call also supplies rent and bonding-curve accounts after the native-token account;
the narrow model recognizes those exact named accounts and does not generalize arbitrary extras.

## Continuity method and scope

`token_continuity.py` carries each observed account's post-state to the next transaction that
references it. Token amount, mint, token program, owner and decimals must agree exactly with
the next pre-state. It processes intervening non-target and failed transactions, so a change
cannot be hidden merely because a transaction lacks a Pump event. Failed transactions may
not change token state. Slot ordering, parent slots and previous-block hashes are checked.

Missing token metadata is never filled with zero. A missing token boundary is classified as
absent only with a zero lamport boundary; on a funded account it is unknown and blocks the
continuity result. Missing transaction metadata, malformed integers, duplicate account indexes
and a gap in the block chain are errors. First observations are left-censored; their previous
history is not claimed to be verified.

Among the 2,791 SOL-passed transactions, the separate native-token replay now matches **5,971**
surviving token observations; **20** need stored-reserve evidence. The count increased because
more transactions passed the SOL gate. New initialization, SyncNative, and closed/reused native
lifetimes still require historical account bytes or equally strong state evidence. Current
account state, inferred rent constants and UI token amounts are insufficient substitutes.

## Next work

1. Work from the exact 82 residual cases in `ECONOMIC_CONTINUITY_VERIFICATION.json`.
   Attribute remaining direct program movements from validated instructions or events.
   Do not solve them from desired post-balances or drop their transactions from the population.
2. Obtain historical native-account state and finish intra-transaction token lifetimes.
   Do not repeat the provider setup or the completed continuity/ordinary fee work.
3. Close binary/IDL, historical config, census and upstream gates before expanding to the
   bounded 1,000-launch pilot. No paid subscription, bulk download or trading was enabled.

## Reproduction

```bash
PYTHONPATH=src python scripts/audit_economic_ledger.py alchemy41-evidence.zip --out economic-full.json
PYTHONPATH=src python scripts/audit_token_continuity.py alchemy41-evidence.zip --out continuity.json
python -m unittest discover -s tests -v
```

Both runners independently reverify the frozen raw/reference hashes before auditing. This
work used zero new blockchain requests. Install the pinned project dependencies first.

- Artifact SHA-256: `bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
- Economic details SHA-256: `82e545f575631bba634ec28497fe8341137dda25cae439908c6c2210e212d322`.
- Continuity end-state digest: `5acf821c02105f2f4a2527cce87e7fee42eaec62310cdbb6aaee024fa1cc3a97`.
- Reports: [`ECONOMIC_CONTINUITY_VERIFICATION.json`](ECONOMIC_CONTINUITY_VERIFICATION.json)
  and [`TOKEN_CONTINUITY_VERIFICATION.json`](TOKEN_CONTINUITY_VERIFICATION.json).
- 14 new tests (208 total) cover migration/extra-account fixtures, tampered amounts and
  recipients, missing companion evidence, removed intervening transactions, block-chain
  gaps, unknown boundaries, account reuse and failed-transaction token changes.

The pinned Pump/PumpSwap IDLs provide instruction roles and event fields. Semantic references:
[Pump program](https://github.com/pump-fun/pump-public-docs/blob/81091419e4457566469d4e2a27f64ed84d42419c/docs/PUMP_PROGRAM_README.md),
[sell accounts](https://github.com/pump-fun/pump-public-docs/blob/81091419e4457566469d4e2a27f64ed84d42419c/docs/instructions/SELL.md),
[creator fee sharing](https://github.com/pump-fun/pump-public-docs/blob/81091419e4457566469d4e2a27f64ed84d42419c/docs/instructions/CREATOR_FEE_SHARING.md).
These are source references, not proof of a historical deployment or profitable signal.
