import argparse
import json
import logging
from pathlib import Path

from .fixtures import synthetic_events
from .pipeline import load_manifest, run
from .rpc import collect
from .preflight import pilot_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description="Meme Quant Lab — EXP-000 research only")
    parser.add_argument("--config",type=Path,default=Path("configs/exp000.json"))
    sub = parser.add_subparsers(dest="command",required=True)
    smoke = sub.add_parser("smoke",help="1000 synthetic launches; NOT empirical validation")
    smoke.add_argument("--out",type=Path,required=True)
    fetch = sub.add_parser("collect",help="Bounded read-only finalized-block download")
    fetch.add_argument("--start-slot",type=int,required=True)
    fetch.add_argument("--end-slot",type=int,required=True)
    fetch.add_argument("--max-slots",type=int,default=100)
    fetch.add_argument("--raw-root",type=Path,default=Path("data/raw"))
    replay = sub.add_parser("replay",help="Verify hashes, decode and reconstruct diagnostic snapshots")
    replay.add_argument("--manifest",type=Path,required=True)
    replay.add_argument("--raw-root",type=Path,default=Path("data/raw"))
    replay.add_argument("--vendor",type=Path,default=Path("vendor"))
    replay.add_argument("--out",type=Path,required=True)
    preflight = sub.add_parser("preflight",help="Audit a completed run against the frozen 1000-launch pilot")
    preflight.add_argument("--report",type=Path,required=True)
    preflight.add_argument("--plan",type=Path,default=Path("configs/pilot1000.json"))
    census = sub.add_parser("census",help="Audit create instructions against scoped events; historical gates stay explicit")
    census.add_argument("--manifest",type=Path,action="append",required=True)
    census.add_argument("--raw-root",type=Path,default=Path("data/raw"))
    census.add_argument("--vendor",type=Path,default=Path("vendor"))
    census.add_argument("--out",type=Path,required=True)
    observe = sub.add_parser("observe-programs",help="Read current metadata of two programs; four bounded public RPC calls")
    observe.add_argument("--raw-root",type=Path,default=Path("data/raw"))
    observe.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
    if args.command in {"census","observe-programs"}:
        from .census import audit_manifests, save_audit
        if args.out.exists():
            parser.error("Output already exists; choose a fresh audit path")
        if args.command == "census":
            result = audit_manifests(args.manifest,args.raw_root,args.vendor)
            save_audit(result,args.out)
            print(json.dumps({k:result[k] for k in ("status","counts","gates")}))
            raise SystemExit(2 if result["status"] == "FAIL" else 0)
        from .regimes import observe_programs
        result = observe_programs(args.raw_root)
        save_audit(result,args.out)
        print(json.dumps({"programs":len(result["programs"]),"issues":result["issues"],"historical_mapping":"UNPROVEN"}))
        return
    if args.command == "preflight":
        result = pilot_readiness(json.loads(args.report.read_text()),json.loads(args.plan.read_text()))
        print(json.dumps(result,indent=2))
        raise SystemExit(2 if result["status"] == "BLOCKED" else 0)
    if args.command == "collect":
        result = collect(args.raw_root,args.start_slot,args.end_slot,args.max_slots)
        print(json.dumps({k:result[k] for k in ["manifest_path","complete","issues"]}))
        return
    config = json.loads(args.config.read_text())
    if args.command == "smoke":
        events,info = synthetic_events(max(1200,config["sample_size"]))
        report = run(events,config,info,args.out)
    else:
        events,info,decoded,issues = load_manifest(args.manifest,args.raw_root,args.vendor)
        report = run(events,config,info,args.out,decoded,issues)
    print(json.dumps({k:report[k] for k in ["status","synthetic","counts","continue_to_exp001"]}))


if __name__ == "__main__":
    main()
