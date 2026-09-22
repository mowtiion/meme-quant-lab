"""EXP-000 diagnostic replay and a fail-closed research gate."""
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .decoder import IDLDecoder, decode_block, normalize_block, PUMP, AMM
from .domain import Event, IntegrityError, canonicalize
from .features import snapshot
from .labels import outcome
from .storage import export_parquet, immutable_write, json_bytes, write_rows


def sample_launches(launches: list[Event], size: int, seed: int) -> list[Event]:
    """Uniform hash ranking of a frozen launch census; no outcome/trade filters."""
    if size <= 0:
        raise IntegrityError("Sample size must be positive")
    by_mint = {}
    for e in launches:
        if e.kind != "create" or not e.success or not e.finalized:
            continue
        if e.mint in by_mint and by_mint[e.mint].event_id != e.event_id:
            raise IntegrityError("Multiple successful creates for the same mint")
        by_mint[e.mint] = e
    rank = lambda e: hashlib.sha256(f"{seed}:{e.mint}".encode()).digest()
    return sorted(by_mint.values(), key=rank)[:size]


def load_manifest(path: Path, raw_root: Path, vendor: Path) -> tuple[list[Event], dict, list[dict], list[dict]]:
    manifest = json.loads(path.read_text())
    if manifest.get("commitment") != "finalized":
        raise IntegrityError("Replay requires finalized block provenance")
    decoders = [IDLDecoder(vendor/f) for f in ("pump.json","pump_amm.json")]
    by_program = {d.program:d for d in decoders}
    events, decoded, issues, times = [], [], list(manifest.get("issues", [])), []
    for block_ref in manifest["blocks"]:
        digest = block_ref["raw_sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise IntegrityError("Invalid raw hash")
        raw_path = raw_root/"objects"/digest[:2]/f"{digest}.json"
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise IntegrityError("Raw payload hash mismatch")
        envelope = json.loads(raw)
        if "error" in envelope or not envelope.get("result"):
            raise IntegrityError("Manifest points to unsuccessful block response")
        block = envelope["result"]
        if block.get("blockTime") is not None:
            times.append(block["blockTime"]*1000)
        rows, block_issues = decode_block(block, block_ref["slot"], digest, by_program)
        normalized, norm_issues = normalize_block(block,rows,by_program[AMM])
        events.extend(normalized)
        decoded.extend(rows)
        issues.extend(block_issues+norm_issues)
    # Verify enumeration bytes independently from the manifest's boolean.
    enumeration_ok = False
    digest = manifest.get("enumeration_sha256")
    if digest:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise IntegrityError("Invalid enumeration hash")
        raw = (raw_root/"objects"/digest[:2]/f"{digest}.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise IntegrityError("Enumeration hash mismatch")
        slots = json.loads(raw)["result"]
        enumeration_ok = (slots == manifest.get("enumerated_slots")
                          and slots == sorted(set(slots))
                          and slots == [b["slot"] for b in manifest["blocks"]]
                          and all(manifest["start_slot"] <= s <= manifest["end_slot"] for s in slots))
    info = {"source":"real_rpc", "synthetic":False,
            "manifest_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "enumeration_complete":enumeration_ok and manifest.get("complete") is True,
            "coverage_start_ms":min(times) if times else None,
            "coverage_end_ms":max(times)-1000 if times else None,
            "blocks":len(manifest["blocks"]),"decoder_hashes":{d.program:d.hash for d in decoders}}
    return events, info, decoded, issues


def run(events: list[Event], config: dict, info: dict, out: Path,
        decoded: list[dict] | None = None, issues: list[dict] | None = None,
        parquet: bool = True) -> dict:
    if out.exists():
        raise IntegrityError("Output already exists; choose a fresh run directory")
    if config.get("live_enabled") or config.get("execution_validated"):
        raise IntegrityError("EXP-000 cannot claim live or execution validation")
    events = canonicalize(events)
    issues = issues or []
    launches = [e for e in events if e.kind=="create" and e.success and e.finalized]
    sample = sample_launches(launches,config["sample_size"],config["seed"])
    groups = defaultdict(list)
    for e in events:
        groups[e.mint].append(e)
    snaps, labels = [], []
    for launch in sample:
        group = groups[launch.mint]
        for age in config["snapshot_seconds"]:
            snap = snapshot(launch,group,age,config["time_mode"],config["boundary_guard_ms"])
            start, end = info.get("coverage_start_ms"), info.get("coverage_end_ms")
            complete = (info.get("enumeration_complete") and not issues and start is not None
                        and start <= launch.event_ms and end is not None and end >= snap["decision_ms"])
            snap["coverage_complete"] = bool(complete)
            if not complete:
                snap["status"] = "INCOMPLETE_COVERAGE"
            snaps.append(snap)
            for horizon in config["horizon_seconds"]:
                # Only synthetic fixtures have a certified complete trade ledger at this stage.
                full_ledger = info.get("synthetic") is True and complete
                labels.append(outcome(snap,group,horizon,end if full_ledger else None,
                                      start if full_ledger else None,config["multiples"],
                                      config["entry_mark_max_age_ms"]))
    synthetic = info.get("synthetic") is True
    gates = {
        "real_launch_sample_1000": "PASS" if not synthetic and len(sample)>=max(1000,config["sample_size"]) else "FAIL",
        "raw_block_coverage": "PASS" if info.get("enumeration_complete") and not synthetic else "FAIL",
        "decoding_and_normalization": "PASS" if events and not issues and not synthetic else "FAIL",
        "complete_snapshot_coverage": "PASS" if snaps and all(s.get("coverage_complete") for s in snaps) and not synthetic else "FAIL",
        "launch_census_independent_reconciliation": "FAIL",
        "historical_idl_regime_validation": "FAIL",
        "pump_swap_cross_venue_ledger": "FAIL",
        "holder_transfer_ledger": "FAIL",
        "creator_wallet_point_in_time_history": "FAIL",
        "observed_availability_and_latency": "FAIL",
        "outcome_coverage_and_entry_reference": "FAIL",
    }
    dataset_version = hashlib.sha256(json_bytes({"events":[asdict(e) for e in events],
                                                "config":config,"info":info})).hexdigest()
    try:
        git_commit = subprocess.check_output(["git","rev-parse","HEAD"],stderr=subprocess.DEVNULL,text=True).strip()
        code_dirty = bool(subprocess.check_output(["git","status","--porcelain"],text=True).strip())
    except subprocess.CalledProcessError:
        git_commit,code_dirty = "UNCOMMITTED",True
    report = {"experiment_id":"MEME-EXP-000", "run_at":datetime.now(timezone.utc).isoformat(),
              "git_commit":git_commit,"code_dirty":code_dirty,"dataset_version":dataset_version,
              "data_provenance":info,"hypothesis":"Historical point-in-time reconstruction is reliable",
              "features":"trade flow and trajectory; other families explicitly unavailable",
              "labels":"diagnostic tape marks only; executable labels NULL",
              "train_window":None,"validation_window":None,"holdout_window":None,
              "parameters":config,"plots":[],"status":"FAIL", "continue_to_exp001":False,
              "reason":"Essential data-integrity gates are unproven or failed; no predictive modelling",
              "synthetic":synthetic,"counts":{"events":len(events),"launch_census":len(launches),
              "sampled_launches":len(sample),"snapshots":len(snaps),"outcomes":len(labels),
              "issues":len(issues)},"gates":gates,
              "feature_families":{
                  "token_market":"FAIL: incomplete regime validation and no certified reserve replay",
                  "trading":"FAIL: no independent complete-ledger reconciliation",
                  "dynamics":"FAIL: algorithms tested; complete historical inputs not established",
                  "distribution":"FAIL: transfer and owner ledger missing",
                  "creator":"FAIL: prior launch history not ingested",
                  "wallets_graphs":"FAIL: prior wallet history and clusters not ingested",
                  "outcomes":"FAIL: horizon coverage and executable entry reference unavailable"},
              "metrics":{"snapshot_status":dict(Counter(s['status'] for s in snaps)),
                         "label_status":dict(Counter(l['status'] for l in labels))},
              "conclusion":"Engineering smoke run only" if synthetic else "Real-data reconnaissance; EXP-000 NOT passed"}
    out.mkdir(parents=True)
    tables = {"events":[asdict(e) for e in events],"launch_sample":[asdict(e) for e in sample],
              "snapshots":snaps,"outcomes":labels,"decoded_events":decoded or [],"issues":issues}
    for name, rows in tables.items():
        write_rows(out/f"{name}.jsonl",rows)
    immutable_write(out/"report.json",json_bytes(report))
    immutable_write(out/"config.json",json_bytes(config))
    if parquet:
        export_parquet(out/"tables",tables)
    lines = ["# MEME-EXP-000 — "+("SYNTHETIC SMOKE TEST" if synthetic else "REAL-DATA RECONNAISSANCE"),
             "", "**Gate: FAIL. EXP-001 blocked.**", "",report["conclusion"],"",
             f"Dataset: `{dataset_version}`",f"Code: `{git_commit}`; dirty: {code_dirty}","",
             "| Count | Value |","|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in report["counts"].items()]
    lines += ["","| Gate | Status |","|---|---|"]
    lines += [f"| {k} | {v} |" for k,v in gates.items()]
    lines += ["","No profitable strategy, valid historical runner rate, executable P&L or live readiness has been demonstrated."]
    immutable_write(out/"report.md",("\n".join(lines)+"\n").encode())
    return report
