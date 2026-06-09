"""GET /stores/{store_id}/metrics — real-time store KPIs. T-18."""

from datetime import date

from fastapi import APIRouter, Depends
import asyncpg

from app.db import get_db
from app.services.metrics import compute_metrics

router = APIRouter(prefix="/stores", tags=["metrics"])


@router.get("/{store_id}/metrics")
async def get_metrics(
    store_id: str,
    for_date: date = None,
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    if for_date is None:
        for_date = date.today()
    return await compute_metrics(store_id, for_date, db)
