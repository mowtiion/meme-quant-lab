# Runtime and residual diagnosis — 2026-09-24

## What was actually slow

The provider connection is working. The elapsed development time has gone into successive
parser variants, evidence checks, tests and publication. It is not the latency of processing
one transaction. Earlier checkpoints did not measure that latency and were insufficient for
assessing realtime readiness.

This change adds a reproducible timing probe and an offline replay that retains one decoded
block at a time, hashes results incrementally, and uses the same transaction checks as the
batch auditor. Batch event attribution now groups rows by transaction once instead of scanning
all events twice for every transaction. No fee formula, ledger gate or economic result changes.

## Measured performance

Both runs reverified the same 41-block archive, decoded all 43,417 transactions, and separately
ran event decoding plus token, SOL and AMM fee checks on all 2,873 successful target transactions.
Single-transaction decoding must equal block decoding. The full economic result digest must equal
the previous checkpoint, including unresolved results. Twenty target transactions were warmed;
Python 3.12.14, Linux x86_64, one worker, normal garbage collection remained enabled.

| Per-target decode plus economic checks | Cached batch | Block-at-a-time replay |
| --- | ---: | ---: |
| Median | 0.84 ms | 0.84 ms |
| 95th percentile | 1.52 ms | 1.59 ms |
| 99th percentile | 2.26 ms | 2.67 ms |
| Largest observation | 182.04 ms | 3.49 ms |
| Sum of per-target work | 2.76 s | 2.63 s |

The cached batch's 182.04 ms outlier included a measured 180.42 ms generation-2 garbage
collection pause. Retaining fewer transaction/result objects removed that large pause in the
streaming sample. Median performance barely changed and p95/p99 were slightly higher; this is
not an across-the-board speedup or proof of a production latency bound.

The streaming replay took **5.80 seconds** including archive-part reading,
block parsing, both decoding paths, result hashing and residual diagnosis. Independent archive
verification took **7.70 seconds** separately; the whole diagnostic took **13.49 seconds**.
The largest recorded GC pause anywhere in the streaming replay, including block loading, was
15.16 ms. Per-transaction numbers exclude block loading and result hashing.
The archive verifier still loads the full historical sample. Bounded replay retention does not
claim that the entire diagnostic has constant memory.

**No live RPC subscription, network latency, persistence latency, queue/backpressure or finality
was measured. This repository is still a research pipeline, not a running live trading system.**
The 41 blocks have integer blockTime endpoints 11 seconds apart; that small, coarsely timestamped
sample cannot establish a production traffic rate or capacity requirement.

## What remains wrong

All 82 unresolved SOL transactions now have instruction bytes, affected accounts, exact
residuals, slot/index, signature and raw block hash in the diagnostic JSONs.

| Observed program association | Transactions | Evidence, not an implemented rule |
| --- | ---: | --- |
| `FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9` | 67 | Residual accounts occur in this program's instruction account lists. The sample includes apparent collection/splitting patterns. No verified instruction/fee mapping yet. |
| `3s1rAymURnacreXreMy718GfqW6kygQsLNka1xDyW8pC` | 15 | Same residual account pair; payer ends at 100,000,000 lamports each time. Only 10 of 15 residual amounts equal that transaction's fee. |

All 82 residual sums are zero, and all affected accounts appear in the associated program's
instruction accounts. This localizes investigation; it does not prove which instruction
made a direct state change, its fee formula, source ownership, or offsetting internal flows.
Both groups stay unresolved. Brand labels from third-party explorers are not treated as an IDL.

Concrete example, slot **449382000 / transaction 44**:

- `2ApLdwLrGayEmxgpLX9BTR47Q2QprfMg5SpjrLeaK8s7`: **-191,973** lamports versus replay.
- `5BqYhuD4q1YD3DMAYkc1FeTu9vqQVYYdfBAmkZjamyZg`: **+112,305** lamports.
- `CD32vhwLbfLnFdaT75C7N2mtXrsPipnT5yybHQzcLvsS`: **+79,668** lamports.

The boundary observations show the net split. Adding an adjustment that merely copies these
observed differences would make the arithmetic pass without explaining the transaction.
That has not been done. Similarly, refunding meta.fee would be wrong for 5 of the 15 other cases.

## Current decision and next substantive milestone

**2,791/2,873 modeled SOL balances pass; 82 remain unresolved.** All 2,663 ordinary AMM fee checks
and 3 separately classified protocol burns still pass. Existing token continuity results are
unchanged. No new blockchain requests, paid services or credentials were needed.

The next evidence milestone is a validated movement mapping for the two identified programs,
using authoritative instruction semantics and applicable historical binary/account-state evidence.
The captured instruction bytes and two real regression fixtures make that investigation reusable.
If authoritative mappings cannot be obtained, these cases remain explicitly quarantined; more
post-balance fitting or repeating provider setup will not solve them.

Historical native reserve/lifecycle proof, binary/config mapping, complete launch census and
provider upstream evidence remain separate gates. The 1,000-launch pilot remains blocked.
A live feed/load test is a separate implementation milestone after its exact input contract is
chosen; this offline replay does not pretend to provide one.

## Reproduce and verify

From the repository root, with installed locked dependencies and PYTHONPATH=src:

```bash
python scripts/diagnose_economic_runtime.py /path/to/alchemy41-evidence.zip --out /tmp/cached-diagnosis.json
python scripts/replay_economic_stream.py /path/to/alchemy41-evidence.zip --out /tmp/stream-replay.json
python -m unittest discover -s tests -v
```

Both commands require and independently verify the pinned archive. Neither accepts an unverified
scratch cache. Both reject decoder failures, block/transaction event differences, or a changed
full economic result hash. All **214 tests** pass locally, including real router residuals,
a one-lamport tamper, non-fee-equivalent replenishment, missing-blockTime benchmark rejection,
and incremental canonical hashing. CI runs the fixture/unit tests, not the private evidence archive.

- Prior main: `560ce6b1c6772290c876d9fc0735fd30f3a2b3ea`.
- Artifact: `bed259be2395aab0deccf1bf31a888b2af22923cc339f242c5c41d37a6c3f6bc`.
- Unchanged details digest: `82e545f575631bba634ec28497fe8341137dda25cae439908c6c2210e212d322`.
- Machine-readable results: [cached](ECONOMIC_RUNTIME_DIAGNOSIS.json), [streaming](ECONOMIC_STREAM_REPLAY.json).
- Earlier continuity proof: [checkpoint](CONTINUITY_CHECKPOINT.md).
