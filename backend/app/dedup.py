"""Deduplication logic for detection events."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from sqlalchemy.orm import Session

from .models import Event

TIME_WINDOW_SEC = 600  # 10 minutes


def compute_grid_key(lat: float, lon: float) -> str:
    """Compute grid key from latitude and longitude (4 decimal places)."""
    return f"{round(lat, 4)}:{round(lon, 4)}"


def compute_time_bucket(timestamp: datetime, window_sec: int = TIME_WINDOW_SEC) -> str:
    """Compute time bucket for deduplication."""
    epoch = datetime(2020, 1, 1, tzinfo=timezone.utc)
    # Make timestamp timezone-aware if it's naive
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    seconds_since_epoch = (timestamp - epoch).total_seconds()
    bucket_number = int(seconds_since_epoch // window_sec)
    return str(bucket_number)


def compute_dedup_group_id(grid_key: str, event_type: str, time_bucket: str) -> str:
    """Compute dedup group ID from grid_key, type, and time bucket."""
    return f"{grid_key}:{event_type}:{time_bucket}"


def find_existing_event(
    db: Session,
    grid_key: str,
    event_type: str,
    timestamp: datetime,
) -> Optional[Event]:
    """
    Find existing event within the time window for the same grid_key and type.
    """
    time_threshold = timestamp - timedelta(seconds=TIME_WINDOW_SEC)
    
    existing = (
        db.query(Event)
        .filter(
            Event.grid_key == grid_key,
            Event.type == event_type,
            Event.last_seen_at >= time_threshold,
        )
        .order_by(Event.last_seen_at.desc())
        .first()
    )
    
    return existing


def process_event(
    db: Session,
    event_type: str,
    bus_id: str,
    lat: float,
    lon: float,
    confidence: float,
    timestamp: datetime,
) -> Tuple[Event, str]:
    """
    Process incoming event with deduplication.
    
    Returns:
        Tuple of (event, kind) where kind is "new" or "update"
    """
    grid_key = compute_grid_key(lat, lon)
    time_bucket = compute_time_bucket(timestamp)
    dedup_group_id = compute_dedup_group_id(grid_key, event_type, time_bucket)
    
    # Check for existing event
    existing = find_existing_event(db, grid_key, event_type, timestamp)
    
    if existing:
        # Update existing event
        existing.last_seen_at = timestamp
        existing.occurrence_count += 1
        # Update confidence if higher
        if confidence > existing.confidence:
            existing.confidence = confidence
        db.commit()
        db.refresh(existing)
        return existing, "update"
    else:
        # Create new event
        new_event = Event(
            id=str(uuid.uuid4()),
            type=event_type,
            bus_id=bus_id,
            first_seen_at=timestamp,
            last_seen_at=timestamp,
            lat=lat,
            lon=lon,
            confidence=confidence,
            grid_key=grid_key,
            occurrence_count=1,
            dedup_group_id=dedup_group_id,
        )
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        return new_event, "new"
