"""POST /events/ingest — idempotent batch ingest. T-16."""

from fastapi import APIRouter, Depends
import asyncpg

from app.db import get_db
from app.models import IngestBatch, IngestResponse

from app.services.ingestion import ingest_batch

router = APIRouter(tags=["ingest"])


@router.post("/events/ingest", response_model=IngestResponse, status_code=200)
async def ingest_events(
    batch: IngestBatch,
    db: asyncpg.Connection = Depends(get_db),
) -> IngestResponse:
    return await ingest_batch(batch.events, db)
