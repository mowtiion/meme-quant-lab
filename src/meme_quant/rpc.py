"""Bounded READ-ONLY RPC collection. No signing, sending, or credentials in logs."""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .domain import IntegrityError
from .storage import immutable_write, json_bytes, store_raw

READ_METHODS = {"getSlot", "getBlocks", "getBlock", "getTransaction", "getSignaturesForAddress", "getBlockTime"}


class RPC:
    def __init__(self, url: str | None = None, min_interval: float = 0.6, attempts: int = 3):
        self.url = url or os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        if not self.url.startswith("https://"):
            raise ValueError("RPC must use HTTPS")
        self.min_interval, self.attempts, self.last = min_interval, attempts, 0.0

    def call(self, method: str, params: list) -> tuple[dict, bytes]:
        if method not in READ_METHODS:
            raise IntegrityError("RPC method not allowed in research mode")
        payload = json_bytes({"jsonrpc":"2.0", "id":1,"method":method,"params":params})
        for attempt in range(self.attempts):
            time.sleep(max(0, self.min_interval-(time.monotonic()-self.last)))
            self.last = time.monotonic()
            request = urllib.request.Request(self.url, data=payload, headers={"Content-Type":"application/json"})
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    raw = response.read()
                envelope = json.loads(raw)
                if "error" in envelope:
                    # Do not log arbitrary provider messages that may contain credentials.
                    raise IntegrityError(f"RPC error code {envelope['error'].get('code')}")
                if "result" not in envelope:
                    raise IntegrityError("Missing RPC result")
                return envelope, raw
            except urllib.error.HTTPError as exc:
                if exc.code not in {429,500,502,503,504} or attempt+1 == self.attempts:
                    raise IntegrityError(f"RPC HTTP {exc.code}") from None
                delay = exc.headers.get("Retry-After", "")
                time.sleep(min(30, max(2**attempt, float(delay) if delay.isdigit() else 0)))
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt+1 == self.attempts:
                    raise IntegrityError("RPC network/timeout failure") from None
                time.sleep(2**attempt)
        raise IntegrityError("RPC retries exhausted")


def collect(root: Path, start: int, end: int, max_slots: int = 100,
            rpc: RPC | None = None) -> dict:
    if start < 0 or end < start or end-start+1 > max_slots:
        raise IntegrityError("Invalid range or slot budget exceeded")
    rpc = rpc or RPC()
    finalized, _ = rpc.call("getSlot", [{"commitment":"finalized"}])
    if end > finalized["result"]:
        raise IntegrityError("Requested range includes non-finalized slots")
    enumerated, raw = rpc.call("getBlocks", [start,end,{"commitment":"finalized"}])
    enumeration_hash, _ = store_raw(root,raw)
    slots = enumerated["result"]
    if not isinstance(slots,list) or slots != sorted(set(slots)) or any(s < start or s > end for s in slots):
        raise IntegrityError("Invalid slot enumeration")
    manifest = {"schema_version":1,"source":"solana_rpc","commitment":"finalized",
                "start_slot":start,"end_slot":end,"enumeration_sha256":enumeration_hash,
                "enumerated_slots":slots,"blocks":[],"issues":[],
                "collected_at":datetime.now(timezone.utc).isoformat(),
                "availability_basis":"historical_download_not_live_arrival",
                "complete":False}
    for slot in slots:
        try:
            envelope, raw = rpc.call("getBlock", [slot,{"encoding":"json","transactionDetails":"full",
                                                     "rewards":False,"commitment":"finalized",
                                                     "maxSupportedTransactionVersion":1}])
            digest, _ = store_raw(root,raw)
            if envelope["result"] is None:
                raise IntegrityError("NULL_BLOCK")
            manifest["blocks"].append({"slot":slot,"raw_sha256":digest})
        except IntegrityError as exc:
            manifest["issues"].append({"slot":slot,"reason":str(exc)})
            break  # No infinite retries or silent skips. Restart with a new manifest.
    manifest["complete"] = len(manifest["blocks"]) == len(slots) and not manifest["issues"]
    encoded = json_bytes(manifest)
    digest, _ = store_raw(root, encoded)
    path = root / "manifests" / f"{digest}.json"
    immutable_write(path,encoded)
    return {**manifest,"manifest_path":str(path)}
