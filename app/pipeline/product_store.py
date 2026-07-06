from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

_lock = asyncio.Lock()
_PATH = Path("data/product_status.json")


def _read_all() -> dict[str, dict]:
    if not _PATH.exists():
        return {}
    return json.loads(_PATH.read_text(encoding="utf-8") or "{}")


def _write_all(data: dict[str, dict]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


async def set_status(product_id: str, status: str, report: dict[str, Any] | None = None,
                      error: str | None = None) -> None:
    async with _lock:
        data = _read_all()
        entry = data.get(product_id, {})
        entry["status"] = status
        if report is not None:
            entry["report"] = report
        if error is not None:
            entry["error"] = error
        data[product_id] = entry
        _write_all(data)


async def get_status(product_id: str) -> dict[str, Any] | None:
    async with _lock:
        return _read_all().get(product_id)
