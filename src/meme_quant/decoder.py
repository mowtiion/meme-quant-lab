"""Pinned Anchor IDL log decoder. Unknown bytes and missing fields are surfaced.

    Logs are attributed to the active program, never to an arbitrary base64 string.
    CPI copies are not ingested again. Missing/truncated logs block completeness.
"""
import base64
import hashlib
import json
import re
from pathlib import Path

from .domain import Event, IntegrityError

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ZERO = "11111111111111111111111111111111"
SOL = "So11111111111111111111111111111111111111112"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"


def base58(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    value = ""
    while n:
        n, r = divmod(n, 58)
        value = ALPHABET[r]+value
    return "1"*(len(data)-len(data.lstrip(b"\0")))+value


def unbase58(value: str) -> bytes:
    n = 0
    for c in value:
        n = n*58+ALPHABET.index(c)
    return b"\0"*(len(value)-len(value.lstrip("1")))+n.to_bytes((n.bit_length()+7)//8,"big")


class Reader:
    def __init__(self, data: bytes, types: dict):
        self.data, self.pos, self.types = data, 0, types

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos+n > len(self.data):
            raise IntegrityError("Truncated Borsh field")
        value = self.data[self.pos:self.pos+n]
        self.pos += n
        return value

    def read(self, spec):
        if isinstance(spec, str):
            if spec == "pubkey":
                return base58(self.take(32))
            if spec == "bool":
                value = self.take(1)[0]
                if value > 1:
                    raise IntegrityError("Invalid Borsh boolean")
                return bool(value)
            if spec == "string":
                return self.take(self.read("u32")).decode("utf-8")
            if re.fullmatch(r"[ui](8|16|32|64|128)", spec):
                return int.from_bytes(self.take(int(spec[1:])//8), "little", signed=spec[0]=="i")
        elif isinstance(spec, dict):
            if "defined" in spec:
                name = spec["defined"]["name"]
                return {f["name"]:self.read(f["type"]) for f in self.types[name]["fields"]}
            if "vec" in spec:
                count = self.read("u32")
                if count > 10000:
                    raise IntegrityError("Oversized Borsh vector")
                return [self.read(spec["vec"]) for _ in range(count)]
            if "array" in spec:
                typ, count = spec["array"]
                return [self.read(typ) for _ in range(count)]
            if "option" in spec:
                return self.read(spec["option"]) if self.read("bool") else None
        raise IntegrityError(f"Unsupported Borsh type: {spec}")


class IDLDecoder:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        self.hash = hashlib.sha256(raw).hexdigest()
        idl = json.loads(raw)
        self.program = idl["address"]
        self.events = {bytes(e["discriminator"]):e["name"] for e in idl["events"]}
        self.types = {t["name"]:t["type"] for t in idl["types"]}
        self.instructions = {bytes(i["discriminator"]):i for i in idl["instructions"]}

    def decode(self, raw: bytes) -> tuple[str, dict]:
        name = self.events.get(raw[:8])
        if name is None:
            raise IntegrityError("Unknown event discriminator")
        reader = Reader(raw[8:], self.types)
        result = {}
        fields = self.types[name]["fields"]
        for i, f in enumerate(fields):
            if reader.pos == len(reader.data):
                result["_missing_trailing_fields"] = [x["name"] for x in fields[i:]]
                break
            result[f["name"]] = reader.read(f["type"])
        if reader.pos != len(reader.data):
            raise IntegrityError("Unknown trailing bytes: IDL version mismatch")
        return name, result


def decode_block(block: dict, slot: int, raw_hash: str, decoders: dict[str, IDLDecoder]) -> tuple[list[dict], list[dict]]:
    decoded, issues = [], []
    if block.get("blockTime") is None:
        return [], [{"slot":slot, "reason":"NULL_BLOCK_TIME"}]
    for tx_index, tx in enumerate(block.get("transactions", [])):
        meta = tx.get("meta")
        if meta is None:
            issues.append({"slot":slot,"tx_index":tx_index,"reason":"NULL_META"})
            continue
        if meta.get("err") is not None:
            continue  # Failed transactions have no committed token-state changes.
        signature = tx["transaction"]["signatures"][0]
        if tx.get("version", "legacy") not in ("legacy", 0, 1):
            issues.append({"slot":slot,"signature":signature,"reason":"UNSUPPORTED_TX_VERSION"})
            continue
        logs = meta.get("logMessages")
        if logs is None:
            issues.append({"slot":slot,"signature":signature,"reason":"MISSING_LOGS"})
            continue
        stack: list[str] = []
        for log_index, log in enumerate(logs):
            invoke = re.fullmatch(r"Program (\w+) invoke \[(\d+)\]", log)
            done = re.match(r"Program (\w+) (success|failed:)", log)
            if invoke:
                program, depth = invoke[1], int(invoke[2])
                if depth != len(stack)+1:
                    issues.append({"slot":slot,"signature":signature,"reason":"LOG_STACK_MISMATCH"})
                stack = stack[:depth-1]+[program]
            elif done:
                if not stack or stack[-1] != done[1]:
                    issues.append({"slot":slot,"signature":signature,"reason":"LOG_STACK_MISMATCH"})
                else:
                    stack.pop()
            elif "Log truncated" in log:
                issues.append({"slot":slot,"signature":signature,"reason":"TRUNCATED_LOGS"})
            elif log.startswith("Program data: ") and stack and stack[-1] in decoders:
                decoder = decoders[stack[-1]]
                try:
                    name, payload = decoder.decode(base64.b64decode(log[14:], validate=True))
                    decoded.append({"slot":slot,"tx_index":tx_index,"event_index":log_index,
                                    "signature":signature,"program":decoder.program,
                                    "event_ms":block["blockTime"]*1000,"name":name,
                                    "payload":payload,"raw_sha256":raw_hash,
                                    "decoder_hash":decoder.hash})
                except (ValueError, UnicodeDecodeError) as exc:
                    issues.append({"slot":slot,"signature":signature,"event_index":log_index,
                                   "reason":"DECODE_ERROR", "detail":str(exc)})
        if stack:
            issues.append({"slot":slot,"signature":signature,"reason":"UNCLOSED_LOG_STACK"})
    return decoded, issues


def normalize_block(block: dict, decoded: list[dict], amm_decoder: IDLDecoder | None = None) -> tuple[list[Event], list[dict]]:
    """Normalize diagnostic trades using only each transaction's own metadata.

    PumpSwap mint identities come from that trade's token accounts, not a future
    pool lookup. Missing accounts/decimals fail closed. This is not reserve replay.
    """
    output, issues = [], []
    kinds = {"CreateEvent":"create", "TradeEvent":"trade", "CompleteEvent":"complete",
             "CompletePumpAmmMigrationEvent":"migration"}
    for row in decoded:
        name, p = row["name"], row["payload"]
        is_amm_trade = row["program"] == AMM and name in {"BuyEvent","SellEvent"}
        if not is_amm_trade and (row["program"] != PUMP or name not in kinds):
            continue
        kind = "trade" if is_amm_trade else kinds[name]
        try:
            if p.get("_missing_trailing_fields"):
                issues.append({"slot":row["slot"],"signature":row["signature"],
                               "reason":"UNVERSIONED_LEGACY_EVENT", "missing":p["_missing_trailing_fields"]})
            tx = block["transactions"][row["tx_index"]]
            meta = tx["meta"]
            decimals = {}
            for balance in meta.get("preTokenBalances", [])+meta.get("postTokenBalances", []):
                m, d = balance["mint"], balance["uiTokenAmount"]["decimals"]
                if m in decimals and decimals[m] != d:
                    raise IntegrityError("Conflicting token decimals")
                decimals[m] = d
            if is_amm_trade:
                keys = tx["transaction"]["message"]["accountKeys"]
                keys = [k["pubkey"] if isinstance(k,dict) else k for k in keys]
                loaded = meta.get("loadedAddresses") or {}
                keys += loaded.get("writable",[])+loaded.get("readonly",[])
                account_mints = {}
                for balance in meta.get("preTokenBalances",[])+meta.get("postTokenBalances",[]):
                    account = keys[balance["accountIndex"]]
                    if account in account_mints and account_mints[account] != balance["mint"]:
                        raise IntegrityError("Token-account mint changed within transaction")
                    account_mints[account] = balance["mint"]
                identities = set()
                if amm_decoder is not None:
                    instructions = list(tx["transaction"]["message"].get("instructions",[]))
                    instructions += [ix for group in meta.get("innerInstructions",[]) for ix in group["instructions"]]
                    for ix in instructions:
                        if keys[ix["programIdIndex"]] != AMM:
                            continue
                        spec = amm_decoder.instructions.get(unbase58(ix["data"])[:8])
                        if not spec or spec["name"] not in {"buy","sell","buy_exact_quote_in"}:
                            continue
                        accounts = {a["name"]:keys[ix["accounts"][i]] for i,a in enumerate(spec["accounts"])
                                    if i < len(ix["accounts"])}
                        if all(accounts.get(k)==p[k] for k in ["pool","user","user_base_token_account","user_quote_token_account"]):
                            identities.add((accounts["base_mint"],accounts["quote_mint"]))
                if len(identities) > 1:
                    raise IntegrityError("Ambiguous pool identity within transaction")
                if identities:
                    mint,quote_mint = identities.pop()
                    for account,expected in [(p["user_base_token_account"],mint),(p["user_quote_token_account"],quote_mint)]:
                        if account in account_mints and account_mints[account] != expected:
                            raise IntegrityError("Instruction mint contradicts token-balance metadata")
                else:
                    mint = account_mints[p["user_base_token_account"]]
                    quote_mint = account_mints[p["user_quote_token_account"]]
                side = "buy" if name=="BuyEvent" else "sell"
                base_raw = p["base_amount_out"] if side=="buy" else p["base_amount_in"]
                quote_raw = p["quote_amount_in"] if side=="buy" else p["quote_amount_out"]
            else:
                mint = p["mint"]
                quote_mint = p.get("quote_mint")
                side = ("buy" if p["is_buy"] else "sell") if kind=="trade" else None
                base_raw,quote_raw = p.get("token_amount"),p.get("quote_amount")
            if quote_mint == ZERO:
                quote_mint = SOL
            # Legacy events without an explicit quote mint are NOT guessed SOL.
            quote_decimals = 9 if quote_mint == SOL else decimals.get(quote_mint)
            common = {k:row[k] for k in ["slot","tx_index","event_index","signature","program",
                                       "event_ms","raw_sha256","decoder_hash"]}
            event = Event(**common, event_id=f"{row['slot']}:{row['signature']}:{row['event_index']}:{row['program']}",
                          mint=mint, kind=kind, wallet=p.get("user"),
                          side=side, base_raw=base_raw, quote_raw=quote_raw,
                          base_decimals=decimals.get(mint), quote_decimals=quote_decimals,
                          quote_mint=quote_mint, extra=p)
            event.validate()
            output.append(event)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            issues.append({"slot":row["slot"],"signature":row["signature"],
                           "reason":"NORMALIZATION_ERROR","detail":str(exc)})
    return output, issues
