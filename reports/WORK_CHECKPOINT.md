# Resume checkpoint — 2026-09-24

## Start here after a reset
The Alchemy access/second-source problem is **resolved for the frozen 41-block sample**.
Read `reports/ALCHEMY_PHASE_B_REPORT.md` and its two verification JSON files first.
Do not repeat account setup or rerun the sample merely because conversation context is lost.

## Verified state
- Alchemy Solana Mainnet enabled with user approval; HTTP 403 resolved.
- PR #5 fixes failed request counting; PR #6 adds narrow UI rounding comparison and phase B.
- Run 36025502200 succeeded at code commit acb788c15b45216242946f97aad584a011b7dbfd.
- 41/41 blocks, 43,417 transactions; 19 exact and 22 canonical comparisons.
- Downloaded artifact independently verified offline; 3,258 decoded / 3,082 normalized events
  match, with zero decode and normalization issues. Includes 5 creates and 3 protocol burns.
- Raw evidence artifact ID 10819402938; expires 2026-10-24. Preserve before expiration.
- Artifact SHA-256: bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc.
- No new API calls are needed to repeat the offline verification.

## Additional completed step: pool reserve replay
Read `reports/RESERVE_LEDGER_REPORT.md` and `RESERVE_LEDGER_VERIFICATION.json`.
2,404 transaction/pool groups, 2,663 ordinary PumpSwap events and 187 pools reconcile
exact integer pre/post vault balances. 250 groups contain multiple events replayed in order.
The 3 protocol burns remain explicitly separate; no other unresolved groups or decoder issues.
Eight known-answer/adversarial tests pass. This work made zero new network requests.

## Additional completed step: token instructions and core fees
Read `reports/TOKEN_LEDGER_REPORT.md` and `TOKEN_LEDGER_VERIFICATION.json`.
2,873 successful target transactions audited; 477 fully reconcile inspected token accounts,
2,360 partial, 36 held back for account reinitialization. 17,186 account observations reconcile.
2,110 AMM core fee checks and all 3 protocol burns pass their scoped checks.
Unresolved: 2,522 WSOL account observations, 63 observations with unsupported instructions,
256 multi-event fee groups, 31 cashback/holder variants, 1 unsupported-instruction fee group.
Residual buyback amount matches; official buyback recipient identity remains unverified.
19 additional tests, including one real fee-split fixture. No new chain requests.

## Additional completed step: SOL/lamport lifecycle replay
Read `reports/LAMPORT_LEDGER_REPORT.md` and `LAMPORT_LEDGER_VERIFICATION.json`.
2,607/2,873 successful target transactions reconcile every account's exact post-lamports.
8,197 native account observations; 32 reused account observations; 2,510 WSOL initializations,
1,704 SyncNative calls, 2,520 WSOL closes in passed transactions. No assumed rent constant.
266 remain open: 234 post-state residuals, 23 modeled intermediate funding deficits,
9 unsupported token instructions (tags 26:3, 39:5, 45:1).
One inspected deficit follows a Pump Sell call before a System transfer; implement direct
program movements from validated semantics/event evidence, never solve gaps from post-state.
13 new tests, including a real two-lifetime WSOL account and one-lamport tamper check.
179 tests pass locally with pinned dependencies. Zero new chain requests.
This is a scoped cash-flow model matching boundaries, not proof of every gross direct program
movement. Stored rent reserve / SyncNative token amounts are not independently verified.
The previous token-ledger and fee results remain separate; their gates are not overwritten.

## Major checkpoint: scoped AMM fees closed
Read `reports/ECONOMIC_CHECKPOINT.md` and `ECONOMIC_LEDGER_VERIFICATION.json` first.
2,786/2,873 SOL transactions pass; 87 remain (82 residuals, four extra sell layouts, one
migration funding deficit). 2,663 ordinary AMM fee events and all three protocol burns pass.
256 multi-event transactions, two cashback and 30 holder-reward events now have exact scopes.
Buyback ATA identity and documented recipient membership verified; historical Global config is not.
5,963 surviving native token observations in SOL-passed transactions match; 18 need stored
reserve evidence. Closed/new lifetimes are not included in that native boundary count.
15 additional tests; all 194 pass locally. Zero chain requests. The previous reports are
historical checkpoints, not current combined results. Reproduce with `audit_economic_ledger.py`.

## Resume action
The provider and scoped AMM fee problems are resolved for this sample. Start with the 87
indexed unresolved cases in the combined JSON, especially four fee-sharing sell layouts and
migration funding. 67 cases invoke FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9; co-occurrence
is not causal attribution. Do not solve residuals from post-state or silently drop transactions.
Obtain historical stored-reserve evidence for SyncNative/new native accounts and finish token
lifetimes / continuity. The old token aggregate gate still holds 36 reused-account transactions.
Then historical binary/IDL mapping, census completeness and provider upstream independence.
The 1,000-launch pilot remains BLOCKED. No bulk collection, paid plan or trading was enabled.
The combined script verifies the existing artifact and makes no blockchain calls.

## Execution route and limits
GitHub is the durable source of code and reports. The initial scratch checkout may be older
than main; fetch current GitHub files rather than overwriting them with old local versions.
The GitHub connector can fetch run lists through the approved actions/runs endpoint, inspect
jobs, download artifacts and update repository files without browser login.

`.github/workflows/alchemy-phase-b.yml` triggers only manually or when
`configs/alchemy_phase_b_request.json` changes on main. Do not change that request marker
unless another bounded run is actually needed. Normal report/code edits do not call Alchemy.
Limits: 42 calls, 192 MiB, 600 seconds, no retries; each completed slot is checkpointed and
raw evidence is uploaded in <=32 MiB parts for 30 days, even after ordinary script failures.
No paid subscription, wallet signing or trading is enabled.

For multi-file GitHub changes, use create_tree/create_commit/update_ref for one commit,
then a PR and CI. Avoid one file per commit triggering redundant CI runs.
