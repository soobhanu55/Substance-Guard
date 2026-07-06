from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import get_settings
from app.models import ReviewQueueItem

_lock = asyncio.Lock()


def _path() -> Path:
    p = Path(get_settings().review_queue_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_all() -> dict[str, dict]:
    path = _path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8") or "{}")


def _write_all(data: dict[str, dict]) -> None:
    _path().write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


async def add_item(item: ReviewQueueItem) -> None:
    async with _lock:
        data = _read_all()
        data[item.id] = json.loads(item.model_dump_json())
        _write_all(data)


async def get_item(item_id: str) -> ReviewQueueItem | None:
    async with _lock:
        data = _read_all()
        raw = data.get(item_id)
        return ReviewQueueItem.model_validate(raw) if raw else None


async def list_items(status: str | None = None) -> list[ReviewQueueItem]:
    async with _lock:
        data = _read_all()
        items = [ReviewQueueItem.model_validate(v) for v in data.values()]
        if status:
            items = [i for i in items if i.status == status]
        return items


async def decide(item_id: str, decision: str, decided_by: str) -> ReviewQueueItem | None:
    from datetime import datetime, timezone
    async with _lock:
        data = _read_all()
        raw = data.get(item_id)
        if raw is None:
            return None
        raw["status"] = decision
        raw["decided_by"] = decided_by
        raw["decided_at"] = datetime.now(timezone.utc).isoformat()
        data[item_id] = raw
        _write_all(data)
        return ReviewQueueItem.model_validate(raw)
