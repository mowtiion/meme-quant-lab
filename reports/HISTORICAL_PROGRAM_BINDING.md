# Historical Pump/PumpSwap executable and interface checkpoint

24 September 2026. **Three historical executable intervals are now pinned and checked against the IDLs.**
The production economic audit rejects an uncovered slot or mismatching IDL before reconciling transactions.
This is limited deployed-interface evidence; the full historical configuration/source/semantics research gate remains open.

| Program regime | Covered slots, inclusive | Deployment slot | Executable SHA-256 |
|---|---|---|---|
| Pump, older pilot | 446462761–447228372 | 446462760 | `7e260ecaa7aef442073042b513d61f8846ad8c5620022db200a76507e2312067` |
| Pump, 41-block sample | 447228374–449734334 | 447228373 | `10ba4b665225573057d59b5b7b8cf2585a5721177a4a0f392f48397f53b59581` |
| PumpSwap | 446462734–450120404 | 446462733 | `feb2ec72199f35999bbfd26ada811a37d297464ab265c78593b2d4717d7d42b5` |

Upgrade slots are deliberately excluded: a slot number alone does not prove whether a transaction preceded or followed the upgrade.
Pump was upgraded again at 449734335; its current bytes must not be substituted for the 41-block sample.
PumpSwap's full observed ProgramData payload, including zero padding, is unchanged since deployment 446462733.
The two finalized ProgramData signature histories cross the lower cutoff; their only successful entries in scope are the documented loader upgrades.
These are public-RPC provenance checks, not independent upstream validation or a cryptographic proof of ledger completeness.

## Reconstructed bytes and persistent evidence

The missing Pump executable was reconstructed from buffer `EPv4PGA1mTBu3oL8UGrpM6a4muN3LseCPKjiXs9mkJw4`:
**1,642,768 bytes; 1,624 loader writes; 1,628 history transactions; 56 blocks; zero coverage holes; zero overwritten bytes.**
One incoming lamport transfer does not change program bytes. Upgrade signature:
`5mfXpjh9SFxVq61V6z31nv3Mvp6UopTpjHdNvqimcWioFHQKrhW5apJxn5UFNSjBRAEixdi3bjotprVAgEPhYGmY`.
The existing strict `buffer_replay.reconstruct` verifies raw hashes, contiguous history receipts, execution, account ordering,
authority, allocation and byte coverage. A new bounded/resumable collector reuses completed blocks.

All three compressed deployed executables and compact RPC/config/upgrade fixtures are committed under `tests/fixtures/historical_programs`.
The expensive raw checkpoint is `meme-quant-pump-program-evidence.zip` (40,399,431 bytes), SHA-256
`c44a0af4ef790ffd552d5f72b756a509a1f94201cecf1095868a35dc4065c963`.
It contains 200,485,456 bytes of hash-addressed selected blocks, exact history receipts, ProgramData/config observations and full reconstruction operations.
Persistent file identity: `libfile_eb9e1a45b4a08191ac82221e9ee68592`.
The older Pump reconstruction remains in the previous historical-binary evidence checkpoint; it was reused without downloading it again.

## Executed verification

Solders LiteSVM executes the actual frozen programs locally, with no RPC submission or wallet signing.

- **126/126 declared instructions** dispatch to the matching handler and deserialize their encoded arguments before failing the deliberately absent-account check.
- **3,135 distinct real argument payloads** from all 2,873 sample transactions plus six launch fixture transactions reach the correct deployed handler.
  This includes historical EOF-tolerant arguments; omitted values are not filled with today's defaults.
- **Nine successful config mutations** exercise cashback, Mayhem and fee settings on all three binaries.
  Only the expected fields change. Three emitted fee-admin events decode completely and carry the changed values.
- A constructed PumpSwap accumulator close reproduces the exact historical close-event CPI bytes and lamport refund.
  The constructed account and successful VM invocation do **not** prove the real truncated invocation committed; its existing quarantine remains intact.
- Wrong selectors, missing required arguments, wrong IDL hashes, uncovered/upgrade slots, overlap, config owner/PDA/discriminator errors,
  backdated snapshots and unknown nonzero account extensions are rejected by regression checks.
- **250 tests pass.** The complete 41-block economic replay remains exactly identical in all transaction detail objects:
  2,873 SOL passes, 20,102 token observations, 2,810 token-bearing transactions and 63 without token-account activity.
  Details SHA-256 remains `7d4682c6ea9e4594c1c30c498c811f9f47e46808a8906be650fde5ff60aacbcc`.

Dispatch and selected state-transition checks are not a whole-program correctness proof. The simulator account state is explicitly synthetic;
its runtime feature set does not certify every historical Solana runtime behavior. Existing native-token historical feature checks remain separate.

## Remaining exact input gap

Four current accounts decode structurally at observed context **450121512**, but are not historical snapshots:

| Account | Address | Expected owner |
|---|---|---|
| Pump Global | `4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf` | Pump |
| PumpSwap GlobalConfig | `ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw` | PumpSwap |
| Pump FeeConfig | `8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt` | `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` |
| PumpSwap FeeConfig | `5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx` | same fee program |

The next state-reconstruction input is those accounts' bytes immediately before the relevant historical window
(e.g. after slot 449381999 for this sample, and 446999999 for the earlier pilot), plus verified relevant mutations thereafter.
An alternative is an independently checked earlier snapshot plus complete mutation history; current values alone cannot establish that history.
The earlier Alchemy probe returned JSON-RPC **-32600**, explicitly denying historical slot parameters on the Free tier
(run 36043100882, artifact 10826973301). No subscription was purchased and no claim is made that purchasing one would guarantee the required data.
The fee program's executable/state semantics also require their own historical validation.

The verified-build service returned no builds for the normalized hashes of any of the three frozen executables.
That is evidence about this service's response, not proof that source code is unavailable everywhere.
Full reproducible-source binding, historical config values, the remaining truncated administrative execution proof,
complete launch census and upstream independence remain open. **EXP-000 and the 1,000-launch pilot stay blocked.**

## Reproduce without new collection

Install `requirements.lock`. Run from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src:tests:scripts python scripts/verify_program_interfaces.py /path/to/alchemy41-evidence.zip --out /tmp/program-interfaces.json
PYTHONPATH=src:scripts python scripts/audit_economic_ledger.py /path/to/alchemy41-evidence.zip --out /tmp/economic.json
```

To recheck the new upload reconstruction, unpack the raw checkpoint into a separate directory and pass its
`data/processed/pump-sample-buffer-blocks.json` and `data/raw` to `meme_quant.buffer_replay.reconstruct` with Pump,
ProgramData `B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu` and the upgrade signature above.
The collector is only for interrupted/missing raw evidence, not a prerequisite for CI or these replay checks.
