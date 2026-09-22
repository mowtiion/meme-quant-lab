"""Diagnostic tape outcomes only. A tape trade is NOT an executable fill."""
from decimal import Decimal
from .domain import Event, canonicalize, IntegrityError


def outcome(snapshot: dict, events: list[Event], horizon_seconds: int,
            complete_through_ms: int | None, coverage_start_ms: int | None,
            multiples: list[int], max_mark_age_ms: int = 30000) -> dict:
    if horizon_seconds <= 0 or any(x <= 1 for x in multiples):
        raise IntegrityError("Invalid label horizon/multiple")
    decision = snapshot["decision_ms"]
    deadline = decision+horizon_seconds*1000
    result = {"mint": snapshot["mint"], "decision_ms": decision,
              "horizon_seconds": horizon_seconds, "label_end_ms": deadline,
              "entry_basis": "last_trade_mark_only_NOT_EXECUTABLE",
              "status": "UNPRICED", "executable_labels_valid": False,
              "forward_return": None, "mfe": None, "mae": None,
              "runner_labels": {str(m): None for m in multiples},
              "diagnostic": None}
    price = snapshot.get("last_trade_price")
    if price is None or snapshot.get("last_trade_age_ms", max_mark_age_ms+1) > max_mark_age_ms:
        return result
    covered = (coverage_start_ms is not None and coverage_start_ms <= decision
               and complete_through_ms is not None and complete_through_ms >= deadline)
    result["status"] = "DIAGNOSTIC_ONLY" if covered else "CENSORED"
    tape = [e for e in canonicalize(events) if e.mint == snapshot["mint"] and e.kind == "trade"
            and e.success and e.finalized and decision < e.event_ms <= deadline]
    if any((e.quote_mint,e.base_decimals,e.quote_decimals) !=
           (snapshot.get("quote_mint"),snapshot.get("base_decimals"),snapshot.get("quote_decimals")) for e in tape):
        raise IntegrityError("Outcome quote units changed")
    entry = Decimal(price)
    ratios = [(e.event_ms, e.price/entry) for e in tape]
    # Unknown coverage can prove a seen threshold hit, but cannot prove no hit.
    hits = {str(m): next((ms-decision for ms, r in ratios if r >= m), None) for m in multiples}
    terminal = tape[-1] if tape else None
    result["diagnostic"] = {
        "mark_entry_price": price, "n_future_trades": len(tape),
        "mark_mfe": str(max([Decimal(1)]+[r for _,r in ratios])-1),
        "mark_mae": str(min([Decimal(1)]+[r for _,r in ratios])-1),
        "time_to_multiple_ms": hits,
        "hit_multiple": {k: True if v is not None else (False if covered else None) for k,v in hits.items()},
        "last_mark_return": (str(terminal.price/entry-1) if terminal and covered
                             and deadline-terminal.event_ms <= max_mark_age_ms else None),
        "terminal_mark_age_ms": deadline-terminal.event_ms if terminal else None,
        "coverage_complete": covered,
    }
    return result
