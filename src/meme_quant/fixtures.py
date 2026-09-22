"""Deterministic synthetic data — NEVER empirical evidence about Solana."""
from .domain import Event


def synthetic_events(count: int = 1200) -> tuple[list[Event], dict]:
    events = []
    start = 1_790_000_000_000
    for i in range(count):
        mint = f"SYNTHETIC_MINT_{i:05d}"
        origin = start+i*1_000_000
        def add(kind, offset, **kw):
            ms = origin+offset
            eid = f"synthetic:{i}:{offset}"
            events.append(Event(event_id=eid,mint=mint,kind=kind,event_ms=ms,slot=ms//1000,
                                tx_index=0,event_index=0,signature=eid,program="synthetic",
                                raw_sha256="synthetic-known-answer",decoder_hash="synthetic-v1",
                                available_ms=ms+200,availability_basis="observed",**kw))
        add("create",0,quote_mint="SOL",extra={"real_token_reserves":1000,"is_mayhem_mode":i%7==0})
        # Include launches with no trades; never screen on activity or success.
        if i%5 == 0:
            continue
        for j,(offset,quote) in enumerate([(9000,1),(10000,2),(30000,3),(400000,12)]):
            add("trade",offset,wallet=f"wallet_{j%2}",side="buy" if j!=2 else "sell",
                base_raw=1_000_000,quote_raw=quote*1_000_000_000,
                base_decimals=6,quote_decimals=9,quote_mint="SOL")
    return events,{"source":"SYNTHETIC_FIXTURE","synthetic":True,"enumeration_complete":True,
                   "coverage_start_ms":start,"coverage_end_ms":start+count*1_000_000+604_800_000}
