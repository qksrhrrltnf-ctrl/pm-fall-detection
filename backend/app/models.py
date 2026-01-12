"""SQLAlchemy models for the event detection system."""

from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Event(Base):
    """Event model for storing detection events with deduplication support."""
    
    __tablename__ = "events"
    
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)  # e.g., "fallen_pm"
    bus_id = Column(String, nullable=False)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    grid_key = Column(String, nullable=False, index=True)
    occurrence_count = Column(Integer, nullable=False, default=1)
    dedup_group_id = Column(String, nullable=False, index=True)
    
    __table_args__ = (
        Index("ix_events_grid_key_type", "grid_key", "type"),
        Index("ix_events_last_seen_at", "last_seen_at"),
    )
    
    def to_dict(self) -> dict:
        """Convert event to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "bus_id": self.bus_id,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "lat": self.lat,
            "lon": self.lon,
            "confidence": self.confidence,
            "grid_key": self.grid_key,
            "occurrence_count": self.occurrence_count,
            "dedup_group_id": self.dedup_group_id,
        }
