"""Point-in-time features: no interpolation, forward fill, or future metadata."""
from decimal import Decimal
from statistics import median

from .domain import Event, IntegrityError, canonicalize


def visible(e: Event, decision_ms: int, mode: str, guard_ms: int) -> bool:
    if mode not in {"chain_replay", "observed"} or guard_ms < 0:
        raise IntegrityError("Invalid time policy")
    if not e.success or not e.finalized or e.event_ms + guard_ms > decision_ms:
        return False
    if mode == "observed":
        return (e.availability_basis == "observed" and e.available_ms is not None
                and e.available_ms <= decision_ms)
    return True


def snapshot(launch: Event, events: list[Event], age_seconds: int,
             mode: str = "chain_replay", guard_ms: int = 1000) -> dict:
    if launch.kind != "create" or age_seconds <= 0:
        raise IntegrityError("Snapshot needs a launch and positive age")
    decision = launch.event_ms + age_seconds * 1000
    if not visible(launch, decision, mode, guard_ms):
        return {"mint": launch.mint, "decision_ms": decision, "age_seconds": age_seconds,
                "status": "UNAVAILABLE_LAUNCH", "time_mode": mode}
    all_events = canonicalize(events)
    seen = [e for e in all_events if e.mint == launch.mint and e.order >= launch.order
            and visible(e, decision, mode, guard_ms)]
    trades = [e for e in seen if e.kind == "trade"]
    units = {(e.quote_mint, e.quote_decimals, e.base_decimals) for e in trades}
    if len(units) > 1:
        raise IntegrityError("Mixed price/volume units; explicit conversion required")
    buys = [e for e in trades if e.side == "buy"]
    sells = [e for e in trades if e.side == "sell"]
    buy_volume = sum((e.quote_volume for e in buys), Decimal(0))
    sell_volume = sum((e.quote_volume for e in sells), Decimal(0))
    volumes = [e.quote_volume for e in trades]
    # Two equal, non-overlapping windows ending at the conservative event cutoff.
    end = decision - guard_ms
    half = age_seconds * 500
    recent = [e for e in trades if end - half < e.event_ms <= end]
    prior = [e for e in trades if end - 2*half < e.event_ms <= end - half]
    seconds = Decimal(half) / 1000
    rate = lambda es: Decimal(len(es)) / seconds
    volume_rate = lambda es: sum((e.quote_volume for e in es), Decimal(0)) / seconds
    first_buy: dict[str, Event] = {}
    for e in buys:
        first_buy.setdefault(e.wallet, e)
    recent_buyers = sum(end-half < e.event_ms <= end for e in first_buy.values())
    prior_buyers = sum(end-2*half < e.event_ms <= end-half for e in first_buy.values())
    curve = [e for e in seen if e.extra.get("real_token_reserves") is not None
             and e.program == launch.program]
    initial = launch.extra.get("real_token_reserves")
    progress = None
    if initial and curve:
        progress = Decimal(1) - Decimal(curve[-1].extra["real_token_reserves"]) / Decimal(initial)
    # Fixed adjacent windows over the second half of observed life. No interpolation.
    # Missing/stale anchor prices yield NULL, never a future backfilled price.
    width_ms = age_seconds * 250
    anchors = [end-2*width_ms, end-width_ms, end]
    def anchor_values(rows, value):
        values = []
        for anchor in anchors:
            eligible = [e for e in rows if e.event_ms <= anchor]
            last = eligible[-1] if eligible else None
            values.append(value(last) if last and anchor-last.event_ms <= width_ms else None)
        return values
    def derivatives(values):
        a, b, c = values
        dt = Decimal(width_ms)/1000
        velocity = (c-b)/dt if b is not None and c is not None else None
        acceleration = (c-2*b+a)/dt**2 if all(v is not None for v in values) else None
        return (str(velocity) if velocity is not None else None,
                str(acceleration) if acceleration is not None else None)
    price_velocity, price_acceleration = derivatives(anchor_values(trades,lambda e:e.price))
    curve_velocity, curve_acceleration = derivatives(anchor_values(
        curve,lambda e:Decimal(1)-Decimal(e.extra["real_token_reserves"])/Decimal(initial))) if initial else (None,None)
    return {
        "mint": launch.mint, "decision_ms": decision, "age_seconds": age_seconds,
        "status": "DIAGNOSTIC_UNVALIDATED", "time_mode": mode,
        "boundary_guard_ms": guard_ms, "event_cutoff_ms": end,
        "last_event_order": list(seen[-1].order) if seen else None,
        "max_feature_event_ms": max((e.event_ms for e in seen), default=None),
        "max_feature_available_ms": max((e.available_ms for e in seen if e.available_ms is not None), default=None),
        "n_buys": len(buys), "n_sells": len(sells), "n_trades": len(trades),
        "unique_buyers": len(first_buy), "unique_sellers": len({e.wallet for e in sells}),
        "buy_volume": str(buy_volume), "sell_volume": str(sell_volume),
        "net_flow": str(buy_volume-sell_volume),
        "median_trade_size": str(median(volumes)) if volumes else None,
        "mean_trade_size": str(sum(volumes)/len(volumes)) if volumes else None,
        "largest_buy": str(max((e.quote_volume for e in buys), default=Decimal(0))),
        "trade_velocity": str(rate(recent)),
        "trade_acceleration": str((rate(recent)-rate(prior))/seconds),
        "buyer_velocity": str(Decimal(recent_buyers)/seconds),
        "buyer_acceleration": str(Decimal(recent_buyers-prior_buyers)/seconds**2),
        "volume_velocity": str(volume_rate(recent)),
        "volume_acceleration": str((volume_rate(recent)-volume_rate(prior))/seconds),
        "price_velocity": price_velocity, "price_acceleration": price_acceleration,
        "curve_velocity": curve_velocity, "curve_acceleration": curve_acceleration,
        "derivative_anchor_times_ms": anchors,
        "last_trade_price": str(trades[-1].price) if trades else None,
        "last_trade_ms": trades[-1].event_ms if trades else None,
        "last_trade_age_ms": decision-trades[-1].event_ms if trades else None,
        "quote_mint": trades[-1].quote_mint if trades else launch.quote_mint,
        "base_decimals": trades[-1].base_decimals if trades else launch.base_decimals,
        "quote_decimals": trades[-1].quote_decimals if trades else launch.quote_decimals,
        "bonding_curve_progress": str(progress) if progress is not None else None,
        "curve_complete": any(e.kind == "complete" for e in seen),
        "migrated": any(e.kind == "migration" for e in seen),
        "regime": {k:launch.extra.get(k) for k in
                   ["is_mayhem_mode", "is_cashback_enabled", "is_holder_reward", "token_program"]},
        "holder_count": None, "top5_concentration": None, "top10_concentration": None,
        "top20_concentration": None, "hhi": None, "creator_holdings": None,
        "wallet_ods": None, "independent_buyers": None,
        "unavailable_reason": "Holder ledger, creator/wallet history and graph evidence not implemented/validated",
    }
