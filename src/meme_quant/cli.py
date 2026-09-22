import argparse
import json
import logging
from pathlib import Path

from .fixtures import synthetic_events
from .pipeline import load_manifest, run
from .rpc import collect


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
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
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
