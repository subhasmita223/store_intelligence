"""GET /stores/{store_id}/heatmap — zone engagement heatmap. T-20."""

from datetime import date

from fastapi import APIRouter, Depends
import asyncpg

from app.db import get_db
from app.services.heatmap import compute_heatmap

router = APIRouter(prefix="/stores", tags=["heatmap"])


@router.get("/{store_id}/heatmap")
async def get_heatmap(
    store_id: str,
    for_date: date = None,
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    if for_date is None:
        for_date = date.today()
    return await compute_heatmap(store_id, for_date, db)
