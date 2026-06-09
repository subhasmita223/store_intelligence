"""GET /stores/{store_id}/funnel — 4-stage conversion funnel. T-19."""

from datetime import date

from fastapi import APIRouter, Depends
import asyncpg

from app.db import get_db
from app.services.funnel import compute_funnel

router = APIRouter(prefix="/stores", tags=["funnel"])


@router.get("/{store_id}/funnel")
async def get_funnel(
    store_id: str,
    for_date: date = None,
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    if for_date is None:
        for_date = date.today()
    return await compute_funnel(store_id, for_date, db)
