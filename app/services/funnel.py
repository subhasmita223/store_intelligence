"""Conversion funnel computation. T-19."""

from datetime import date
from typing import Any

import asyncpg

from app.services.session import build_sessions


async def compute_funnel(
    store_id: str,
    for_date: date,
    conn: asyncpg.Connection,
) -> dict[str, Any]:
    sessions = await build_sessions(store_id, for_date, conn)
    customer = [s for s in sessions if not s.is_staff]

    counts = [
        len(customer),
        sum(1 for s in customer if s.reached_zone_visit),
        sum(1 for s in customer if s.reached_billing),
        sum(1 for s in customer if s.completed_purchase),
    ]
    labels = ["ENTRY", "ZONE_VISIT", "BILLING_QUEUE", "PURCHASE"]

    stages = []
    for i, (label, count) in enumerate(zip(labels, counts)):
        prev = counts[i - 1] if i > 0 else count
        drop_off = round((1 - count / prev) * 100, 1) if prev > 0 and i > 0 else 0.0
        stages.append({"stage": label, "count": count, "drop_off_pct": drop_off})

    return {"store_id": store_id, "stages": stages}
