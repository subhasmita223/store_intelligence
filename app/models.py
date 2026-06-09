"""Pydantic event schema — single source of truth for the event contract. T-02."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class EventType(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    ZONE_ENTERED = "zone_entered"
    ZONE_EXITED = "zone_exited"
    QUEUE_COMPLETED = "queue_completed"
    QUEUE_ABANDONED = "queue_abandoned"


# ── Entry / Exit ──────────────────────────────────────────────────────────────

class EntryExitEvent(BaseModel):
    event_type: Literal["entry", "exit"]
    id_token: str
    store_code: str
    camera_id: str
    event_timestamp: datetime
    is_staff: bool
    gender_pred: Optional[Literal["M", "F"]] = None
    age_pred: Optional[int] = None
    age_bucket: Optional[str] = None
    is_face_hidden: bool = False
    group_id: Optional[str] = None
    group_size: Optional[int] = None


# ── Zone presence ─────────────────────────────────────────────────────────────

class ZoneEvent(BaseModel):
    event_type: Literal["zone_entered", "zone_exited"]
    track_id: int
    store_id: str
    camera_id: str
    zone_id: str
    zone_name: str
    zone_type: str
    is_revenue_zone: Literal["Yes", "No"]
    event_time: datetime
    zone_hotspot_x: float
    zone_hotspot_y: float
    gender: Optional[Literal["M", "F"]] = None
    age: Optional[int] = None
    age_bucket: Optional[str] = None


# ── Billing queue ─────────────────────────────────────────────────────────────

class QueueEvent(BaseModel):
    queue_event_id: UUID
    event_type: Literal["queue_completed", "queue_abandoned"]
    track_id: int
    store_id: str
    camera_id: str
    zone_id: str
    zone_name: str
    zone_type: Literal["BILLING"]
    is_revenue_zone: Literal["Yes", "No"]
    queue_join_ts: datetime
    queue_served_ts: Optional[datetime] = None
    queue_exit_ts: datetime
    wait_seconds: int
    queue_position_at_join: int
    abandoned: bool
    zone_hotspot_x: float
    zone_hotspot_y: float
    gender: Optional[Literal["M", "F"]] = None
    age: Optional[int] = None
    age_bucket: Optional[str] = None


# ── Discriminated union — the wire type ──────────────────────────────────────

StoreEvent = Annotated[
    Union[EntryExitEvent, ZoneEvent, QueueEvent],
    Field(discriminator="event_type"),
]


# ── Ingest contract ───────────────────────────────────────────────────────────

class IngestBatch(BaseModel):
    events: list[StoreEvent] = Field(max_length=500)


class IngestError(BaseModel):
    index: int
    event_type: Optional[str] = None
    message: str


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: list[IngestError] = []
