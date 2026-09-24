"""Pinned Anchor IDL log decoder. Unknown bytes and missing fields are surfaced.

    Logs are attributed to the active program, never to an arbitrary base64 string.
    Truncated logs use a scoped, execution-verified CPI fallback when possible.
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
                fields = self.types[name]["fields"]
                if fields and not all(isinstance(f, dict) and 'name' in f for f in fields):
                    return [self.read(f) for f in fields]
                return {f["name"]:self.read(f["type"]) for f in fields}
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
        self.accounts = {a['name']:bytes(a['discriminator']) for a in idl.get('accounts',[])}
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
        transaction_start, issue_start = len(decoded), len(issues)
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
        starts: list[int] = []
        for log_index, log in enumerate(logs):
            invoke = re.fullmatch(r"Program (\w+) invoke \[(\d+)\]", log)
            done = re.match(r"Program (\w+) (success|failed:)", log)
            if invoke:
                program, depth = invoke[1], int(invoke[2])
                if depth != len(stack)+1:
                    issues.append({"slot":slot,"signature":signature,"reason":"LOG_STACK_MISMATCH"})
                stack = stack[:depth-1]+[program]
                starts = starts[:depth-1]+[len(decoded)]
            elif done:
                if not stack or stack[-1] != done[1]:
                    issues.append({"slot":slot,"signature":signature,"reason":"LOG_STACK_MISMATCH"})
                else:
                    start = starts.pop()
                    if done[2] == "failed:":
                        del decoded[start:]  # A caught CPI failure rolls back its children too.
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
        transaction_issues = issues[issue_start:]
        reasons = {i["reason"] for i in transaction_issues}
        if "TRUNCATED_LOGS" in reasons and reasons <= {"TRUNCATED_LOGS", "UNCLOSED_LOG_STACK"}:
            from .cpi import recover_transaction
            try:
                recovered, recovery_issues = recover_transaction(
                    tx, decoded[transaction_start:], slot, tx_index, block["blockTime"]*1000,
                    raw_hash, decoders, transaction_issues)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                issues.append({"slot":slot,"signature":signature,"reason":"CPI_RECOVERY_REJECTED",
                               "detail":str(exc)})
            else:
                decoded[transaction_start:] = recovered
                issues[issue_start:] = recovery_issues
    return decoded, issues


def boost_identity(block: dict, row: dict, decoded: list[dict], decoder: IDLDecoder):
    """Certify a single boost action against instruction, companion event and balances.

    Multi-action transactions remain quarantined until instruction-scoped balance
    replay exists. A sentinel account alone is never evidence of a protocol buy.
    """
    p = row["payload"]
    tx = block["transactions"][row["tx_index"]]
    meta = tx["meta"]
    keys = list(tx["transaction"]["message"]["accountKeys"])
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in keys]
    loaded = meta.get("loadedAddresses") or {}
    keys += loaded.get("writable", []) + loaded.get("readonly", [])
    instructions = list(tx["transaction"]["message"].get("instructions", []))
    instructions += [ix for g in meta.get("innerInstructions", []) for ix in g["instructions"]]
    candidates = []
    for ix in instructions:
        if keys[ix["programIdIndex"]] != AMM:
            continue
        raw = unbase58(ix["data"])
        spec = decoder.instructions.get(raw[:8])
        if spec and spec["name"] == "boost_buy_and_burn":
            a = {a["name"]: keys[ix["accounts"][i]] for i, a in enumerate(spec["accounts"])}
            if a["pool"] == p["pool"]:
                candidates.append((a, raw))
    peers = [r for r in decoded if r["tx_index"] == row["tx_index"]
             and r["program"] == AMM and r["payload"].get("pool") == p["pool"]]
    companions = [r for r in peers if r["name"] == "BoostBuyAndBurnEvent"]
    buys = [r for r in peers if r["name"] in {"BuyEvent", "SellEvent"}]
    if len(candidates) != 1 or len(companions) != 1 or len(buys) != 1:
        raise IntegrityError("Boost requires one instruction, one buy and one companion")
    a, raw = candidates[0]
    c = companions[0]["payload"]
    if c.get("_missing_trailing_fields") or p.get("_missing_trailing_fields"):
        raise IntegrityError("Incomplete boost event")
    if not (a["boost_vault_authority"] == p["user"]
            and a["boost_vault"] == p["user_quote_token_account"]
            and a["base_mint"] == c["mint"] and a["authority"] == c["authority"]
            and p["timestamp"] == c["timestamp"]
            and p["base_amount_out"] == c["base_amount_burned"]
            and p["quote_amount_in"] == c["quote_amount_in_used"]
            and p["virtual_quote_reserves"] == c["virtual_quote_reserves"]):
        raise IntegrityError("Boost instruction/event mismatch")
    if len(raw) != 24 or int.from_bytes(raw[8:16], "little") != c["quote_amount_in_requested"]:
        raise IntegrityError("Boost instruction amount mismatch")
    if not (0 < c["quote_amount_in_used"] <= c["quote_amount_in_requested"]
            and c["base_amount_burned"] >= int.from_bytes(raw[16:24], "little")):
        raise IntegrityError("Boost limits mismatch")
    balances = []
    for field in ("preTokenBalances", "postTokenBalances"):
        balances.append({keys[b["accountIndex"]]: b for b in meta[field]})
    expected = [("pool_base_token_account", "base_mint", -c["base_amount_burned"],
                 p["pool_base_token_reserves"], c["base_reserves_after"]),
                ("pool_quote_token_account", "quote_mint", c["quote_amount_in_used"],
                 p["pool_quote_token_reserves"], c["real_quote_reserves_after"]),
                ("boost_vault", "quote_mint", -c["quote_amount_in_used"],
                 p["user_quote_token_reserves"], c["boost_vault_remaining"])]
    for account, mint, delta, before, after in expected:
        pre, post = (b[a[account]] for b in balances)
        if pre["mint"] != a[mint] or post["mint"] != a[mint]:
            raise IntegrityError("Boost balance mint mismatch")
        if (int(pre["uiTokenAmount"]["amount"]) != before
                or int(post["uiTokenAmount"]["amount"]) != after or after-before != delta):
            raise IntegrityError("Boost balance reconciliation failed")
    burns = []
    for ix in instructions:
        if keys[ix["programIdIndex"]] != a["base_token_program"]:
            continue
        data = unbase58(ix["data"])
        if len(data) == 9 and data[0] == 8:  # SPL Token / Token-2022 Burn
            accounts = [keys[i] for i in ix["accounts"]]
            if accounts[:3] == [a["pool_base_token_account"], a["base_mint"], a["pool"]]:
                burns.append(int.from_bytes(data[1:], "little"))
    if burns != [c["base_amount_burned"]]:
        raise IntegrityError("Boost burn instruction mismatch")
    return a["base_mint"], a["quote_mint"], companions[0]["event_index"]


def normalize_block(block: dict, decoded: list[dict], amm_decoder: IDLDecoder | None = None) -> tuple[list[Event], list[dict]]:
    """Normalize diagnostic trades using only each transaction's own metadata.

    PumpSwap mint identities come from that trade's token accounts, not a future
    pool lookup. Missing accounts/decimals fail closed. This is not reserve replay.
    """
    output, issues, matched_companions = [], [], set()
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
            extra = p
            if is_amm_trade and name == "BuyEvent" and p["user_base_token_account"] == ZERO:
                if amm_decoder is None:
                    raise IntegrityError("Boost identity requires pinned AMM instructions")
                mint, quote_mint, companion = boost_identity(block, row, decoded, amm_decoder)
                kind, side = "protocol_buy_burn", None
                base_raw, quote_raw = p["base_amount_out"], p["quote_amount_in"]
                extra = {**p, "economic_actor": "protocol", "companion_event_index": companion,
                         "reconciliation": "instruction_event_burn_and_pre_post_balances"}
            elif is_amm_trade:
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
            if row.get("event_source") == "verified_self_cpi":
                extra = {**extra, "recovery": {k: row[k] for k in (
                    "event_source", "instruction_path", "parent_instruction_path",
                    "source_log_index", "recovered_missing_log", "recovery_original_issues")}}
            event = Event(**common, event_id=f"{row['slot']}:{row['signature']}:{row['event_index']}:{row['program']}",
                          mint=mint, kind=kind, wallet=None if kind=="protocol_buy_burn" else p.get("user"),
                          side=side, base_raw=base_raw, quote_raw=quote_raw,
                          base_decimals=decimals.get(mint), quote_decimals=quote_decimals,
                          quote_mint=quote_mint, extra=extra)
            event.validate()
            output.append(event)
            if kind == "protocol_buy_burn":
                matched_companions.add((row["tx_index"], companion))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            issues.append({"slot":row["slot"],"signature":row["signature"],
                           "event_index":row["event_index"],
                           "reason":"NORMALIZATION_ERROR","detail":str(exc)})
    for row in decoded:
        if (row["program"] == AMM and row["name"] == "BoostBuyAndBurnEvent"
                and (row["tx_index"], row["event_index"]) not in matched_companions):
            issues.append({"slot":row["slot"], "signature":row["signature"],
                           "event_index":row["event_index"], "reason":"UNMATCHED_BOOST_COMPANION"})
    return output, issues
