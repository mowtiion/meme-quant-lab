"""Content-addressed raw envelopes, immutable files, deterministic table output."""
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      default=lambda v: str(v) if isinstance(v, Decimal) else asdict(v)).encode()


def immutable_write(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as f:
            f.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite immutable file: {path}")
    return hashlib.sha256(content).hexdigest()


def store_raw(root: Path, response: bytes) -> tuple[str, Path]:
    digest = hashlib.sha256(response).hexdigest()
    path = root / "objects" / digest[:2] / f"{digest}.json"
    immutable_write(path, response)
    return digest, path


def write_rows(path: Path, rows: list[dict]) -> None:
    immutable_write(path, b"".join(json_bytes(x) + b"\n" for x in rows))


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def export_parquet(directory: Path, tables: dict[str, list[dict]]) -> None:
    """Raw payload JSON is retained verbatim; Parquet is a reproducible projection.

    Nested records are serialized as JSON to keep missing/all-null Arrow types stable.
    Raw chain u64 values stay in payload_json (never lossy double conversion).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    import duckdb

    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.glob("*.parquet")) or (directory / "research.duckdb").exists():
        raise ValueError("Use a fresh output directory; derived versions are immutable")
    with duckdb.connect(str(directory / "research.duckdb")) as con:
        for name, rows in tables.items():
            if not name.replace("_", "").isalnum():
                raise ValueError("Unsafe table name")
            projected = []
            for row in rows:
                projected.append({
                    "mint": row.get("mint"), "event_id": row.get("event_id"),
                    "decision_ms": row.get("decision_ms"), "event_ms": row.get("event_ms"),
                    "kind": row.get("kind"), "status": row.get("status"),
                    "payload_json": json_bytes(row).decode(),
                })
            schema = pa.schema([("mint", pa.string()), ("event_id", pa.string()),
                                ("decision_ms", pa.int64()), ("event_ms", pa.int64()),
                                ("kind", pa.string()), ("status", pa.string()),
                                ("payload_json", pa.string())])
            table = pa.Table.from_pylist(projected, schema=schema)
            target = directory / f"{name}.parquet"
            pq.write_table(table, target, compression="zstd")
            con.from_parquet(str(target)).create(name)
