"""FastAPI backend for the PM Detection System."""

import os
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import init_db, get_db
from .models import Event
from .dedup import process_event
from .realtime import broadcaster, broadcast_event

# Create data directory if not exists
os.makedirs("./data", exist_ok=True)

# Initialize database
init_db()

app = FastAPI(
    title="PM Detection System",
    description="Bus camera-based fallen PM detection with GPS integration",
    version="1.0.0",
)

# Static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# Pydantic models
class DetectionEventInput(BaseModel):
    """Input model for detection events from simulator."""
    type: str
    bus_id: str
    lat: float
    lon: float
    confidence: float
    timestamp: str  # ISO8601 format


class EventResponse(BaseModel):
    """Response model for events."""
    id: str
    type: str
    bus_id: str
    first_seen_at: str
    last_seen_at: str
    lat: float
    lon: float
    confidence: float
    grid_key: str
    occurrence_count: int
    dedup_group_id: str


class EventResultResponse(BaseModel):
    """Response model for POST /events."""
    kind: str  # "new" or "update"
    event: EventResponse


@app.get("/")
async def index():
    """Serve the dashboard."""
    return FileResponse(static_path / "index.html")


@app.post("/events", response_model=EventResultResponse)
async def create_event(
    event_input: DetectionEventInput,
    db: Session = Depends(get_db),
):
    """
    Receive a detection event, apply deduplication, and store/update in database.
    Broadcasts the event to SSE subscribers.
    """
    try:
        timestamp = datetime.fromisoformat(event_input.timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid timestamp format")
    
    event, kind = process_event(
        db=db,
        event_type=event_input.type,
        bus_id=event_input.bus_id,
        lat=event_input.lat,
        lon=event_input.lon,
        confidence=event_input.confidence,
        timestamp=timestamp,
    )
    
    event_dict = event.to_dict()
    
    # Broadcast to SSE subscribers
    broadcast_event(kind, event_dict)
    
    return EventResultResponse(kind=kind, event=EventResponse(**event_dict))


@app.get("/events", response_model=List[EventResponse])
async def list_events(
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """
    List events from the last N hours.
    """
    threshold = datetime.utcnow() - timedelta(hours=hours)
    
    events = (
        db.query(Event)
        .filter(Event.last_seen_at >= threshold)
        .order_by(Event.last_seen_at.desc())
        .all()
    )
    
    return [EventResponse(**event.to_dict()) for event in events]


@app.get("/stream")
async def stream_events():
    """
    SSE endpoint for real-time event updates.
    """
    queue = broadcaster.subscribe()
    
    async def event_generator():
        try:
            async for message in broadcaster.stream(queue):
                yield message
        finally:
            broadcaster.unsubscribe(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
