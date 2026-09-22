"""Canonical normalized event contract. Raw chain integers never become floats."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class IntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class Event:
    event_id: str
    mint: str
    kind: str
    event_ms: int
    slot: int
    tx_index: int
    event_index: int
    signature: str
    program: str
    raw_sha256: str
    decoder_hash: str
    available_ms: int | None = None
    availability_basis: str = "unknown"
    success: bool = True
    finalized: bool = True
    wallet: str | None = None
    side: str | None = None
    base_raw: int | None = None
    quote_raw: int | None = None
    base_decimals: int | None = None
    quote_decimals: int | None = None
    quote_mint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def order(self) -> tuple[int, int, int]:
        return self.slot, self.tx_index, self.event_index

    def validate(self) -> None:
        if self.kind not in {"create", "trade", "complete", "migration", "pool_create", "transfer"}:
            raise IntegrityError(f"Unknown event kind: {self.kind}")
        for key in ("event_ms", "slot", "tx_index", "event_index"):
            x = getattr(self, key)
            if type(x) is not int or x < 0:
                raise IntegrityError(f"Invalid {key}")
        if not all((self.event_id, self.mint, self.signature, self.raw_sha256, self.decoder_hash)):
            raise IntegrityError("Missing provenance")
        if self.available_ms is not None and (type(self.available_ms) is not int or self.available_ms < 0):
            raise IntegrityError("Invalid availability timestamp")
        if self.availability_basis not in {"unknown", "observed", "assumed"}:
            raise IntegrityError("Invalid availability basis")
        if self.kind == "trade":
            if self.side not in {"buy", "sell"} or not self.wallet or not self.quote_mint:
                raise IntegrityError("Missing trade identity/side/quote unit")
            for key in ("base_raw", "quote_raw"):
                x = getattr(self, key)
                if type(x) is not int or not 0 < x < 2**64:
                    raise IntegrityError(f"Invalid {key}")
            for key in ("base_decimals", "quote_decimals"):
                x = getattr(self, key)
                if type(x) is not int or not 0 <= x <= 18:
                    raise IntegrityError(f"Unknown/invalid {key}")

    @property
    def quote_volume(self) -> Decimal:
        if self.quote_raw is None or self.quote_decimals is None:
            raise IntegrityError("Unknown quote units")
        return Decimal(self.quote_raw) / Decimal(10)**self.quote_decimals

    @property
    def price(self) -> Decimal:
        self.validate()
        if self.kind != "trade":
            raise IntegrityError("Price requires a trade")
        return self.quote_volume / (Decimal(self.base_raw) / Decimal(10)**self.base_decimals)


def canonicalize(events: list[Event]) -> list[Event]:
    """Identical repeat deliveries collapse; conflicting copies stop the run."""
    by_id: dict[str, Event] = {}
    by_order: dict[tuple, str] = {}
    for e in events:
        e.validate()
        if e.event_id in by_id and e != by_id[e.event_id]:
            raise IntegrityError(f"Conflicting duplicate: {e.event_id}")
        order = (e.program, *e.order)
        if order in by_order and by_order[order] != e.event_id:
            raise IntegrityError("Ambiguous event ordering")
        by_id[e.event_id] = e
        by_order[order] = e.event_id
    result = sorted(by_id.values(), key=lambda e: e.order)
    times_by_slot: dict[int, int] = {}
    for e in result:
        if e.slot in times_by_slot and times_by_slot[e.slot] != e.event_ms:
            raise IntegrityError("Inconsistent blockTime within slot")
        times_by_slot[e.slot] = e.event_ms
    if any(b < a for a, b in zip(times_by_slot.values(), list(times_by_slot.values())[1:])):
        raise IntegrityError("Non-monotone block times require explicit adjudication")
    return result
