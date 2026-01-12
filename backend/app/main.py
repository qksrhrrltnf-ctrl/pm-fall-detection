"""FastAPI backend for the PM Detection System."""

import os
import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import init_db, get_db, SessionLocal
from .models import Event
from .dedup import process_event
from .realtime import broadcaster, broadcast_event

# Create data directory if not exists
os.makedirs("./data", exist_ok=True)

# Initialize database
init_db()

# Auto-simulation settings
AUTO_SIM_ENABLED = os.getenv("AUTO_SIM_ENABLED", "true").lower() == "true"
AUTO_SIM_INTERVAL_MIN = int(os.getenv("AUTO_SIM_INTERVAL_MIN", "15"))  # seconds
AUTO_SIM_INTERVAL_MAX = int(os.getenv("AUTO_SIM_INTERVAL_MAX", "30"))  # seconds

# Seoul city center area for random events
SEOUL_CENTER = {"lat": 37.5665, "lon": 126.9780}
LOCATION_VARIANCE = 0.02  # ~2km radius

BUS_IDS = ["bus-1", "bus-2", "bus-3", "bus-4", "bus-5"]


def generate_random_event():
    """Generate a random PM fall detection event."""
    lat = SEOUL_CENTER["lat"] + random.uniform(-LOCATION_VARIANCE, LOCATION_VARIANCE)
    lon = SEOUL_CENTER["lon"] + random.uniform(-LOCATION_VARIANCE, LOCATION_VARIANCE)
    confidence = random.uniform(0.5, 0.99)
    bus_id = random.choice(BUS_IDS)
    
    return {
        "type": "fallen_pm",
        "bus_id": bus_id,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "confidence": round(confidence, 2),
        "timestamp": datetime.now(timezone.utc),
    }


async def auto_simulation_task():
    """Background task that generates random events periodically."""
    while True:
        try:
            # Wait random interval
            interval = random.randint(AUTO_SIM_INTERVAL_MIN, AUTO_SIM_INTERVAL_MAX)
            await asyncio.sleep(interval)
            
            # Generate and process event
            event_data = generate_random_event()
            
            db = SessionLocal()
            try:
                event, kind = process_event(
                    db=db,
                    event_type=event_data["type"],
                    bus_id=event_data["bus_id"],
                    lat=event_data["lat"],
                    lon=event_data["lon"],
                    confidence=event_data["confidence"],
                    timestamp=event_data["timestamp"],
                )
                
                event_dict = event.to_dict()
                broadcast_event(kind, event_dict)
                print(f"[Auto-Sim] Generated {kind} event: {event.id[:8]}... at ({event.lat}, {event.lon})")
            finally:
                db.close()
                
        except Exception as e:
            print(f"[Auto-Sim] Error: {e}")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    if AUTO_SIM_ENABLED:
        print("[Auto-Sim] Starting background simulation...")
        task = asyncio.create_task(auto_simulation_task())
    
    yield
    
    # Shutdown
    if AUTO_SIM_ENABLED:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="PM Detection System",
    description="Bus camera-based fallen PM detection with GPS integration",
    version="1.0.0",
    lifespan=lifespan,
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


class DemoResponse(BaseModel):
    """Response model for demo endpoint."""
    message: str
    events_created: int


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


@app.post("/demo", response_model=DemoResponse)
async def generate_demo_events(
    count: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Generate demo events for testing/demonstration.
    Creates random PM fall detection events.
    """
    events_created = 0
    
    for _ in range(count):
        event_data = generate_random_event()
        
        event, kind = process_event(
            db=db,
            event_type=event_data["type"],
            bus_id=event_data["bus_id"],
            lat=event_data["lat"],
            lon=event_data["lon"],
            confidence=event_data["confidence"],
            timestamp=event_data["timestamp"],
        )
        
        event_dict = event.to_dict()
        broadcast_event(kind, event_dict)
        events_created += 1
        
    return DemoResponse(
        message=f"Successfully generated {events_created} demo events",
        events_created=events_created,
    )


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
    return {"status": "healthy", "auto_sim": AUTO_SIM_ENABLED}
