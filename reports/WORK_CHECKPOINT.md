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

## Resume action
Prioritize a lamport/SOL account-lifecycle ledger on the same verified artifact to explain
wrapped-SOL creation, SyncNative, closing and reuse. Do not infer historical rent constants or
missing balances from the desired answer. Then address multi-action fee attribution,
cashback/holder rewards, unsupported Token-2022 instructions and buyback recipient provenance.
Modules: `token_ledger.py`, `fee_audit.py`, `reserve_ledger.py`; scripts:
`audit_token_ledger.py`, `audit_reserve_ledger.py` (PYTHONPATH=src, offline).
The complete ledger, historical census, binary/IDL mapping, upstream independence and
1,000-launch pilot gates remain open. No live trading or bulk collection has been enabled.

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
