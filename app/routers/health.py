"""GET /health — service status and feed staleness. T-22."""

from fastapi import APIRouter, Depends
import asyncpg

from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    store_rows = await db.fetch(
        """
        SELECT store_id, MAX(event_ts) AS last_event_at
        FROM events
        GROUP BY store_id
        """
    )

    stores = {}
    for r in store_rows:
        last = r["last_event_at"]
        if last is None:
            status = "NO_DATA"
        else:
            stale_check = await db.fetchval(
                "SELECT NOW() - $1::timestamptz > INTERVAL '10 minutes'", last
            )
            status = "STALE_FEED" if stale_check else "OK"
        stores[r["store_id"]] = {
            "last_event_at": last.isoformat() if last else None,
            "feed_status": status,
        }

    return {"status": "OK", "database": "connected", "stores": stores}
