# Token account lifecycles resolved — 24 September 2026

The frozen 41-block sample now has no unresolved SOL or token-account movements.
The full original archive was hash-verified and all 2,873 successful target transactions
were decoded and replayed again. This completes the sample account-ledger milestone;
it does not clear the separate research or full mint-supply-history gates.

| Check | Result |
|---|---:|
| SOL transactions | 2,873 / 2,873 exact |
| Transactions with token accounts | 2,810 / 2,810 exact |
| Transactions with no token-account activity | 63, explicitly not applicable |
| Token account observations | 20,102 / 20,102 exact |
| Distinct intra-transaction account lifetimes | 20,140 |
| Previously held reinitialization transactions | 36 / 36 resolved |
| Previously unverified surviving WSOL boundaries | 20 / 20 resolved |
| All surviving WSOL boundaries | 6,118 / 6,118 exact |
| Native initializations / SyncNative calls / closes | 2,605 / 1,752 / 2,606 |
| UnwrapLamports instruction | 1 / 1 resolved |
| Ordinary AMM fee checks / protocol burns | 2,663 / 3 exact |
| Local regression suite | 239 passed, including 17 new tests |

## Actual cause and implementation

The aggregate token checker merged all uses of one address. A close followed by a new
initialization was therefore held as `ACCOUNT_REINITIALIZATION`; WSOL initialization,
synchronization and closing were also unresolved. The production economic audit now
replays token amounts chronologically with a separate generation for each lifetime.
Transfers, minting, burning and unwrapping update the currently active generation.
Non-native accounts must be empty before closure. Native closures explicitly remove
the remaining wrapped units, while the existing SOL ledger independently returns the
entire live lamport balance, including reserve and any unsynchronized deposit.

Crucially, this historical classic-token binary recomputes the native reserve on
**SyncNative**, using the runtime Rent sysvar. It replaces both the stored reserve and
token amount. Assuming the older rule, which reused the previously stored reserve,
would require historical account bytes that this binary does not consume for its
calculation.

The public program account and ProgramData establish deployment at slot **419472000**,
before the sample. The frozen binary's rent arithmetic and native account writes are
executed in bytecode-slice tests. It enforces a classic account size of **165 bytes**.
Public feature accounts establish threshold deprecation at **407376000**, rate 6333
at **444096000**, and rate **5080** at **446256000**. The later reduction and safeguard
features were unactivated at the finalized observation. The observed Rent sysvar is
5080 with threshold 1. The applicable reserve is therefore:

`(165 + 128) * 5080 = 1,488,440 lamports`

This rate comes from feature activation evidence and program arithmetic, never a fitted
post-balance residual. Initialization and synchronization take instruction-time lamports
from the independently reconciled SOL trace. Post-token amounts are comparison-only.
The rule is deliberately restricted to the verified sample slots 449382000–449382040;
other periods or native Token-2022 lifecycles require their own applicable evidence.

The new ledger also decodes opcode 45: omitted amount unwraps the current token amount;
an explicit amount subtracts only that amount and leaves the account open. Existing
fee attribution retains its scoped gross-flow parser. The older standalone amount-only
audit remains conservative; `audit_economic_ledger.py` is the current combined checker.

## Independent checks and preservation

All **2,873 complete SOL result objects** and **2,873 fee-result lists** are byte-for-byte
identical to the preceding router milestone. Every previously reconciled token observation
(**17,240**) retains its exact before, after and instruction delta. The 36 formerly held
transactions and 20 formerly unknown surviving native boundaries are individually indexed
with signatures in [the verification JSON](TOKEN_LIFECYCLE_VERIFICATION.json).

Tests cover real reused accounts, transient and surviving WSOL, existing-account sync,
ordinary and Token-2022 closure, protocol burning and native unwrap. Adversarial checks
reject one-unit post-token corruption, old rent assumptions, missing historical rule
context, missing instruction-time cash state, reinitialization before close, unsupported
instructions and unverified cash replay. Deployed machine-code slices independently test
reserve multiplication, native initialization, SyncNative overwrites and unwrap subtraction.
These are arithmetic/branch tests, not a claim of a complete historical validator replay
or whole-program source-to-binary reproducible build.

## Retrieval route

Three bounded public mainnet RPC requests fetched program/rent accounts, ProgramData,
and rent-feature accounts. An Alchemy demo request returned HTTP 403. The repository-secret
probe first made 12 reads which returned HTTP 400; a subsequent three-read diagnostic
preserved the exact response: ordinary account access works, historical slot parameters
return **-32600, unavailable on the Free tier**. Runs 36042955363 and 36043100882 preserve
that evidence. No paid plan was enabled. Feature activation records and the deployed binary
provided the required alternative, so that provider restriction does not block this milestone.

Evidence and pinned source references: [TOKEN_NATIVE_RULES.json](TOKEN_NATIVE_RULES.json).
The raw original sample archive retains SHA-256
`bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
New complete result digest:
`7d4682c6ea9e4594c1c30c498c811f9f47e46808a8906be650fde5ff60aacbcc`.

## Reproduce and resume

From the repository root, with locked dependencies installed:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/audit_economic_ledger.py /path/to/alchemy41-evidence.zip --out /tmp/token-lifecycle-full.json
```

No network is needed for these checks. The legacy SOL-only native-boundary diagnostics
still show their conservative 20 reserve holds; they are intentionally retained unchanged.
The combined token ledger separately resolves all 20, and the summary labels the old counts
as `legacy_rent_independent_native_boundary_counts` to avoid confusing them with open work.

Next: historical Pump/PumpSwap binary/config/IDL applicability, the remaining quarantined
administrative execution evidence, complete launch census and provider upstream provenance.
Do not reopen the solved router or WSOL investigations. The 1,000-launch pilot remains
blocked on those research gates; sample account correctness does not establish a trading edge.
