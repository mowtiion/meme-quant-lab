import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from meme_quant.decoder import Reader, IDLDecoder, decode_block, normalize_block, base58
from meme_quant.domain import Event, IntegrityError, canonicalize
from meme_quant.features import snapshot, visible
from meme_quant.labels import outcome
from meme_quant.pipeline import sample_launches, run
from meme_quant.rpc import RPC, collect
from meme_quant.storage import immutable_write, store_raw


BASE = 1_000_000


def event(kind="trade", seconds=1, index=0, **kw):
    ms = BASE+seconds*1000
    common = dict(event_id=f"{kind}:{seconds}:{index}",mint="mint",kind=kind,
                  event_ms=ms,slot=seconds+1000,tx_index=index,event_index=0,
                  signature=f"signature:{seconds}:{index}",program="program",raw_sha256="rawhash",
                  decoder_hash="decoderhash",available_ms=ms+200,availability_basis="observed")
    if kind=="trade":
        common.update(wallet="buyer",side="buy",base_raw=1_000_000,quote_raw=1_000_000_000,
                      base_decimals=6,quote_decimals=9,quote_mint="SOL")
    common.update(kw)
    return Event(**common)


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.launch=event("create",0,extra={"is_mayhem_mode":False,"real_token_reserves":1000})

    def test_exact_cutoff_and_one_millisecond_after(self):
        at=event(seconds=10)
        after=replace(at,event_id="after",event_ms=BASE+10001,slot=1011)
        snap=snapshot(self.launch,[self.launch,at,after],10,guard_ms=0)
        self.assertEqual(snap["n_trades"],1)
        self.assertEqual(snap["max_feature_event_ms"],BASE+10000)

    def test_default_guard_excludes_boundary_second(self):
        snap=snapshot(self.launch,[self.launch,event(seconds=9),event(seconds=10)],10)
        self.assertEqual(snap["n_trades"],1)

    def test_late_arrival_is_not_visible_at_earlier_decision(self):
        trade=event(seconds=1,available_ms=BASE+20000)
        s=snapshot(self.launch,[self.launch,trade],10,mode="observed")
        self.assertEqual(s["n_trades"],0)

    def test_assumed_latency_never_counts_as_observed(self):
        e=event(availability_basis="assumed")
        self.assertFalse(visible(e,BASE+10000,"observed",0))

    def test_future_extreme_trade_does_not_change_features(self):
        past=[self.launch,event(seconds=1)]
        future=event(seconds=11,quote_raw=10**16)
        self.assertEqual(snapshot(self.launch,past,10),snapshot(self.launch,past+[future],10))

    def test_future_migration_and_regime_do_not_leak(self):
        future=event("migration",11,extra={"is_mayhem_mode":True})
        s=snapshot(self.launch,[self.launch,future],10)
        self.assertFalse(s["migrated"])
        self.assertFalse(s["regime"]["is_mayhem_mode"])

    def test_failed_and_nonfinalized_trades_are_excluded(self):
        s=snapshot(self.launch,[self.launch,event(success=False),event(seconds=2,finalized=False)],10)
        self.assertEqual(s["n_trades"],0)

    def test_zero_activity_launch_is_kept_with_unknown_price(self):
        s=snapshot(self.launch,[self.launch],10)
        self.assertEqual(s["n_trades"],0)
        self.assertIsNone(s["last_trade_price"])
        self.assertIsNone(s["holder_count"])

    def test_nonvisible_launch_is_not_backdated(self):
        launch=replace(self.launch,available_ms=BASE+20000)
        self.assertEqual(snapshot(launch,[launch],10,mode="observed")["status"],"UNAVAILABLE_LAUNCH")

    def test_distinct_wallets_are_not_claimed_independent(self):
        s=snapshot(self.launch,[self.launch,event(wallet="a"),event(seconds=2,wallet="b")],10)
        self.assertEqual(s["unique_buyers"],2)
        self.assertIsNone(s["independent_buyers"])

    def test_hand_calculated_flow_and_acceleration(self):
        events=[self.launch,event(seconds=1,quote_raw=2*10**9),
                event(seconds=6,wallet="b",quote_raw=3*10**9),
                event(seconds=8,side="sell",quote_raw=10**9)]
        s=snapshot(self.launch,events,10,guard_ms=0)
        self.assertEqual(Decimal(s["buy_volume"]),5)
        self.assertEqual(Decimal(s["sell_volume"]),1)
        self.assertEqual(Decimal(s["net_flow"]),4)
        self.assertEqual(Decimal(s["trade_velocity"]),Decimal("0.4"))
        self.assertEqual(Decimal(s["trade_acceleration"]),Decimal("0.04"))

    def test_mixed_quote_units_rejected(self):
        with self.assertRaises(IntegrityError):
            snapshot(self.launch,[self.launch,event(),event(seconds=2,quote_mint="USDC",quote_decimals=6)],10)


class DataIntegrity(unittest.TestCase):
    def test_duplicate_delivery_is_idempotent(self):
        e=event()
        self.assertEqual(canonicalize([e,e]),[e])

    def test_conflicting_duplicate_stops_run(self):
        e=event()
        with self.assertRaises(IntegrityError):
            canonicalize([e,replace(e,quote_raw=7)])

    def test_decimal_precision(self):
        e=event(base_raw=2**63,quote_raw=2**63+1,base_decimals=9,quote_decimals=9)
        self.assertGreater(e.price,Decimal(1))

    def test_noninteger_raw_amount_rejected(self):
        with self.assertRaises(IntegrityError):
            event(quote_raw=1.1).validate()

    def test_missing_decimals_rejected(self):
        with self.assertRaises(IntegrityError):
            event(base_decimals=None).validate()

    def test_same_slot_inconsistent_timestamp_rejected(self):
        with self.assertRaises(IntegrityError):
            canonicalize([event(),event(seconds=2,slot=1001,index=1)])

    def test_regressing_block_time_rejected(self):
        with self.assertRaises(IntegrityError):
            canonicalize([event(seconds=2,slot=1001),event(seconds=1,slot=1002)])

    def test_immutable_raw_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"raw.json"
            immutable_write(p,b"first")
            immutable_write(p,b"first")
            with self.assertRaises(ValueError):
                immutable_write(p,b"second")
            self.assertEqual(p.read_bytes(),b"first")

    def test_stable_content_hash(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(store_raw(Path(d),b"x"),store_raw(Path(d),b"x"))

    def test_sampling_independent_of_input_order(self):
        launches=[event("create",i,mint=str(i)) for i in range(100)]
        a=sample_launches(launches,50,42)
        self.assertEqual(a,sample_launches(list(reversed(launches)),50,42))
        self.assertNotEqual(a,sample_launches(launches,50,43))

    def test_duplicate_launches_do_not_gain_sampling_weight(self):
        e=event("create",0)
        self.assertEqual(len(sample_launches([e,e],1000,42)),1)


class Labels(unittest.TestCase):
    def setUp(self):
        self.launch=event("create",0)
        self.past=event(seconds=9)
        self.snap=snapshot(self.launch,[self.launch,self.past],10)

    def label(self,events,covered=True):
        return outcome(self.snap,events,30,BASE+40000 if covered else None,BASE,[2,5,10])

    def test_labels_strictly_after_decision_and_at_horizon(self):
        trades=[event(seconds=10,quote_raw=100*10**9),event(seconds=40,quote_raw=5*10**9),
                event(seconds=41,quote_raw=1000*10**9)]
        label=self.label(trades)
        self.assertEqual(label["diagnostic"]["n_future_trades"],1)
        self.assertEqual(label["diagnostic"]["time_to_multiple_ms"]["5"],30000)
        self.assertFalse(label["diagnostic"]["hit_multiple"]["10"])

    def test_censored_absence_is_not_failure(self):
        label=self.label([],covered=False)
        self.assertEqual(label["status"],"CENSORED")
        self.assertIsNone(label["diagnostic"]["hit_multiple"]["2"])

    def test_observed_hit_survives_censoring(self):
        label=self.label([event(seconds=11,quote_raw=2*10**9)],covered=False)
        self.assertTrue(label["diagnostic"]["hit_multiple"]["2"])

    def test_no_trade_at_entry_is_not_replaced_with_future_price(self):
        s=snapshot(self.launch,[self.launch],10)
        label=outcome(s,[event(seconds=11)],30,BASE+40000,BASE,[2])
        self.assertEqual(label["status"],"UNPRICED")

    def test_tape_marks_never_become_execution_labels(self):
        label=self.label([event(seconds=12,quote_raw=100*10**9)])
        self.assertFalse(label["executable_labels_valid"])
        self.assertIsNone(label["forward_return"])
        self.assertIsNone(label["runner_labels"]["10"])

    def test_stale_terminal_price_not_reported_as_horizon_return(self):
        label=outcome(self.snap,[event(seconds=11)],300,BASE+310000,BASE,[2])
        self.assertIsNone(label["diagnostic"]["last_mark_return"])

    def test_unknown_coverage_start_is_not_complete(self):
        label=outcome(self.snap,[],30,BASE+999999,None,[2])
        self.assertEqual(label["status"],"CENSORED")


class DecoderAndRPC(unittest.TestCase):
    def test_real_amm_non_sol_quote_and_raw_amounts(self):
        root=Path(__file__).resolve().parents[1]
        f=json.loads((root/"tests/fixtures/real_amm_trade.json").read_text())
        decoder=IDLDecoder(root/"vendor/pump_amm.json")
        rows,issues=decode_block(f,f["slot"],f["raw_block_sha256"],{decoder.program:decoder})
        self.assertEqual(issues,[])
        events,issues=normalize_block(f,rows,decoder)
        self.assertEqual(issues,[])
        e=events[0]
        self.assertEqual(e.quote_mint,"Xsa62P5mvPszXL1krVUnU5ar38bBSVcWAB6fmPCo5Zu")
        self.assertEqual(e.base_raw,21961416445)
        self.assertEqual(e.quote_raw,314055)
        self.assertEqual(e.side,"sell")

    def test_real_v1_transaction_known_amounts(self):
        root=Path(__file__).resolve().parents[1]
        fixture=json.loads((root/"tests/fixtures/real_pump_trade.json").read_text())
        decoder=IDLDecoder(root/"vendor/pump.json")
        rows,issues=decode_block(fixture,fixture["slot"],fixture["raw_block_sha256"],{decoder.program:decoder})
        self.assertEqual(issues,[])
        trades=[r for r in rows if r["name"]=="TradeEvent"]
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]["payload"]["quote_amount"],97777777)
        self.assertEqual(trades[0]["payload"]["token_amount"],1922563020299)
        events,issues=normalize_block(fixture,rows)
        self.assertEqual(issues,[])
        self.assertEqual(events[0].quote_decimals,9)
        self.assertEqual(events[0].base_decimals,6)

    def test_borsh_rejects_partial_field_and_invalid_bool(self):
        with self.assertRaises(IntegrityError):
            Reader(b"\x01",{}).read("u64")
        with self.assertRaises(IntegrityError):
            Reader(b"\x02",{}).read("bool")

    def test_base58_zero_pubkey(self):
        self.assertEqual(base58(bytes(32)),"1"*32)

    def test_untrusted_program_data_not_parsed(self):
        block={"blockTime":123,"transactions":[{"version":1,"transaction":{"signatures":["sig"]},
               "meta":{"err":None,"logMessages":["Program unrelated invoke [1]",
               "Program data: not_base64", "Program unrelated success"]}}]}
        rows,issues=decode_block(block,1,"hash",{})
        self.assertEqual(rows,[])
        self.assertEqual(issues,[])

    def test_null_time_is_not_zero(self):
        rows,issues=decode_block({"blockTime":None},1,"hash",{})
        self.assertEqual(issues[0]["reason"],"NULL_BLOCK_TIME")

    def test_send_transaction_disallowed(self):
        with self.assertRaises(IntegrityError):
            RPC().call("sendTransaction",["anything"])

    def test_slot_budget_enforced_before_network(self):
        with self.assertRaises(IntegrityError):
            collect(Path("unused"),1,1000,max_slots=10)

    def test_partial_collection_never_claims_complete(self):
        class FakeRPC:
            def call(self,method,params):
                if method=="getBlock": raise IntegrityError("RPC HTTP 429")
                result=100 if method=="getSlot" else [1,2]
                return {"result":result},json.dumps({"result":result}).encode()
        with tempfile.TemporaryDirectory() as d:
            r=collect(Path(d),1,2,rpc=FakeRPC())
            self.assertFalse(r["complete"])
            self.assertEqual(len(r["issues"]),1)

    def test_synthetic_run_cannot_unlock_modelling(self):
        with tempfile.TemporaryDirectory() as d:
            cfg={"sample_size":1,"seed":42,"snapshot_seconds":[10],"horizon_seconds":[30],
                 "time_mode":"chain_replay","boundary_guard_ms":1000,"multiples":[2],"entry_mark_max_age_ms":30000}
            report=run([event("create",0)],cfg,{"synthetic":True,"enumeration_complete":True,
                       "coverage_start_ms":BASE,"coverage_end_ms":BASE+999999},Path(d)/"out",parquet=False)
            self.assertEqual(report["status"],"FAIL")
            self.assertFalse(report["continue_to_exp001"])


if __name__ == "__main__":
    unittest.main()
