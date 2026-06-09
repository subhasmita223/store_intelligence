"""GET /stores/{store_id}/anomalies — active operational anomalies. T-21."""

from fastapi import APIRouter, Depends
import asyncpg

from app.db import get_db
from app.services.anomalies import detect_anomalies

router = APIRouter(prefix="/stores", tags=["anomalies"])


@router.get("/{store_id}/anomalies")
async def get_anomalies(
    store_id: str,
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    return {"store_id": store_id, "anomalies": await detect_anomalies(store_id, db)}
