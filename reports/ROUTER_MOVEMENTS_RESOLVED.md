# Router movements resolved — 2026-09-24

**All 2,873 successful target transactions now reconcile every modeled SOL end balance.**
The 82 remaining cases are resolved: 67 FLASH distributions and 15 balance replenishments.
The original 2,791 passing transaction results are byte-for-byte unchanged. Token-account
and AMM-fee results are unchanged in all 2,873 transactions, including the newly resolved 82.

## Verified executable evidence

A bounded public Solana RPC lookup retrieved both upgradeable Program accounts and their
ProgramData. The finalized ProgramData observation slot was **450107290**. Both last upgrades
precede the frozen sample (449382000–449382040), so the retrieved deployed binaries cover it.
The executable data, metadata headers, hashes and exact movement code slices are frozen under
`tests/fixtures/`; subsequent checks require no network access or disassembler dependency.

| Program | Last upgrade | ProgramData | SHA-256 of complete executable allocation |
| --- | ---: | --- | --- |
| `FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9` | 449187226 | `GsDbRnSMyWpwKn9AMXLLNYbjeDhoVmqC6vK9Srh2FDmB` | `dca7c9c1306fb3fd12c98605bc1fa37a9bbd7986e92e4f0a62fe9abe325ccfae` |
| `3s1rAymURnacreXreMy718GfqW6kygQsLNka1xDyW8pC` | 447884446 | `6iaRPA6MaXu8Ad2brgQXjzMW5MYZwju2XJ35KapamGxK` | `c6d92441d184de9e749fad0de1551b855c7374311c694a674a8a3b4aae01c799` |

Source: `https://api.mainnet-beta.solana.com`, finalized `getMultipleAccounts` responses.
Three successful read-only program-state requests were used, including the initial availability
probe. No paid API, credentials, trading, transaction submission, or new block download.
Third-party brand labels and guessed IDLs are not relied on for the movement rules.

## FLASH: encoded distribution and two-stage integer rounding

The observed instruction tags are single bytes: `0` route, `1` preparation, `5` preparation,
and `7` account-free self-event. Seven route layouts occur in the 67 cases. The route payload
contains tag + two u64 amounts + direction + route-length + route bytes + two rate bytes.
The validated route bytes are `2c`, `2b`, `2a00`, `0d0e2e00`, `2d0e0d00`, `2a0e0d00`.
Direction and exact account count distinguish the seventh layout.

For every route, the final child instruction is an explicit System transfer from account 1
into the vault at account -5. Its independently encoded amount is F. It was already modeled
as incoming SOL. The missing operation distributes that money directly from the program-owned
vault, so it does not produce further System-transfer CPIs.

The two trailing instruction bytes are D and Q. The actual binary at virtual addresses
`0x0e58–0x1598` implements, within the supported rates/layouts:

```
weighted = F * (200 - D)
net = weighted // 200
referral_1 = (net * Q) // 200
referral_2 = (net * 3) // 100
referral_3 = weighted // 10000
primary = F - sum(payments to present referral accounts)
```

The three referral destinations are accounts -4, -3, -2. The program ID is the absent-account
sentinel. Account -1 must remain absent in the supported layout; the separately encoded fourth
referral and privileged high-rate variants are explicitly rejected. Account 2 receives the
remaining fee. Payments are scheduled immediately after the successful funding instruction.
No post-balance differences participate in these calculations.

The initial single-expression hypothesis explained 66 cases, but failed slot 449382025 / index 32
by one lamport. F=4,776,442, D=50, Q=90 yields **1,612,048** with the binary's two divisions;
collapsing them into one expression yields **1,612,049**. The implementation preserves the
instruction order. Across the sample it adds 70 nonzero referral payments and 67 remainders.

## 3s1rA: replenish account 8 to 0.1 SOL

The deployed entrypoint contains the missing branch at `0x9aa58–0x9ae00`. It reads account 8's
current lamports, computes the shortfall to **100,000,000**, and subtracts it from account 0
before crediting account 8. AccountInfo array offsets `0x008` and `0x188` select accounts 0
and 8 (48-byte stride). It skips replenishment when the destination already meets/exceeds the
target, or when account 0 cannot fund the whole shortfall.

The supported successful instruction layouts are tag 0 / 38 accounts and tag 1 / 42 accounts,
both six instruction bytes. The replay evaluates the shortfall against its live balance after
child execution, with the transaction fee already deducted exactly once.

This explains why a fee-only refund failed on five cases: the payer could start below the
target balance. Example slot 449382007 / index 255 starts at 99,979,600; after its 5,100 fee,
99,974,500 remains and the binary replenishes **25,500**, not 5,100. All 15 cases now match.

## Independent checks and outcome

The tests execute the frozen machine-code slices with a small strict SBPF interpreter; they do
not merely repeat the Python formulas. FLASH checks include 100 deterministic randomized input
sets plus rounding/zero cases and varied absent recipients. Replenishment checks include exact
thresholds, over-target balances, zero balance, and insufficient funding. This is an isolated
movement-code execution check, not a claim to replay every Solana syscall or the entire program.

Real regression fixtures cover every observed route layout, multiple referral levels, small
payments, the one-lamport rounding edge, both replenishment tags, and a mint/account-creation case.
Changing post balances cannot change predicted movements. Changing the payer's starting balance
changes the replenishment correctly. Unsupported layouts, ambiguous funding and slots outside the
verified deployment interval remain rejected.

All **222 tests** pass locally.

The complete economic audit reverified the 41-block evidence archive, decoded all blocks and
replayed all 2,873 successful target transactions. Results:

- SOL passes: **2,873**; residuals/layout/funding errors: **0**.
- Previously correct full transaction results unchanged: **2,791**.
- Ordinary AMM fee checks: **2,663**; protocol burns: **3**, unchanged.
- Full economic details SHA-256: `1cfead15257c6b61119ede122c057aad7024cfb3c16533fdf4d750328f16446d`.
- Verification and all 82 resolved transaction identities/movements: `ROUTER_MOVEMENT_VERIFICATION.json`.

The 82-case SOL debugging goal is complete. This does not close unrelated historical native-token
reserve/supply, Pump binary/config, full census or upstream-independence gates. EXP-000's wider
research pilot remains blocked on those separate requirements; no financial edge is claimed.
The old timing and residual reports remain historical snapshots. No new benchmark was performed.

Reproduce from the repo root with locked dependencies and PYTHONPATH=src:

```bash
python -m unittest discover -s tests -v
python scripts/audit_economic_ledger.py /path/to/alchemy41-evidence.zip --out /tmp/router-replay.json
```
