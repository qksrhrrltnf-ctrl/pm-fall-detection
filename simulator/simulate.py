#!/usr/bin/env python3
"""
Simulator for generating mock PM detection events.

Generates fake DetectionEvents with:
- type: "fallen_pm" (fixed)
- confidence: 0.5~0.99 random
- bus_id: configurable (default "bus-1")
- timestamp: ISO8601 based on simulation time
- lat/lon: linearly interpolated from route.json
- Event occurrence controlled by frame ranges and probabilities
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Event generation zones: (start_frame, end_frame, probability)
EVENT_ZONES: List[Tuple[int, int, float]] = [
    (50, 120, 0.25),   # 50~120 프레임에서 p=0.25로 이벤트 발생
    (200, 240, 0.4),   # 200~240 프레임에서 p=0.4로 이벤트 발생
    (350, 400, 0.3),   # 350~400 프레임에서 p=0.3로 이벤트 발생
]


def load_route(route_path: Path) -> List[Dict[str, float]]:
    """Load route from JSON file."""
    if route_path.exists():
        with open(route_path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # Generate default circular route around Seoul City Hall
        print(f"Route file not found at {route_path}, generating default route...")
        return generate_default_route()


def generate_default_route() -> List[Dict[str, float]]:
    """Generate a default circular route around Seoul City Hall."""
    import math
    
    center_lat = 37.5665
    center_lon = 126.9780
    radius = 0.01  # roughly 1km
    num_points = 100
    
    route = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        lat = center_lat + radius * math.sin(angle)
        lon = center_lon + radius * 1.2 * math.cos(angle)  # Adjust for latitude distortion
        route.append({"lat": lat, "lon": lon})
    
    return route


def interpolate_position(
    route: List[Dict[str, float]], 
    progress: float
) -> Tuple[float, float]:
    """
    Interpolate position along the route based on progress (0.0 to 1.0).
    """
    if not route:
        return 37.5665, 126.9780
    
    # Handle edge cases
    progress = max(0.0, min(1.0, progress))
    
    # Calculate position in route
    total_segments = len(route) - 1
    if total_segments <= 0:
        return route[0]["lat"], route[0]["lon"]
    
    exact_position = progress * total_segments
    segment_index = int(exact_position)
    segment_progress = exact_position - segment_index
    
    # Handle last point
    if segment_index >= total_segments:
        return route[-1]["lat"], route[-1]["lon"]
    
    # Linear interpolation between two points
    p1 = route[segment_index]
    p2 = route[segment_index + 1]
    
    lat = p1["lat"] + (p2["lat"] - p1["lat"]) * segment_progress
    lon = p1["lon"] + (p2["lon"] - p1["lon"]) * segment_progress
    
    return lat, lon


def should_generate_event(frame: int, zones: List[Tuple[int, int, float]]) -> bool:
    """
    Determine if an event should be generated at this frame.
    """
    for start, end, probability in zones:
        if start <= frame <= end:
            return random.random() < probability
    return False


def create_event(
    bus_id: str,
    lat: float,
    lon: float,
    timestamp: datetime,
) -> Dict[str, Any]:
    """Create a detection event."""
    return {
        "type": "fallen_pm",
        "bus_id": bus_id,
        "lat": lat,
        "lon": lon,
        "confidence": round(random.uniform(0.5, 0.99), 2),
        "timestamp": timestamp.isoformat(),
    }


def create_session_with_retry() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,  # exponential backoff: 1, 2, 4, 8, 16 seconds
        status_forcelist=[500, 502, 503, 504],
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


def send_event(
    session: requests.Session,
    backend_url: str,
    event: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Send event to backend with retry logic."""
    url = f"{backend_url}/events"
    
    try:
        response = session.post(url, json=event, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to send event: {e}")
        return None


def wait_for_backend(backend_url: str, max_retries: int = 30, delay: float = 2.0) -> bool:
    """Wait for backend to be available."""
    print(f"Waiting for backend at {backend_url}...")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{backend_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"Backend is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        
        print(f"  Attempt {attempt + 1}/{max_retries} - Backend not ready, waiting...")
        time.sleep(delay)
    
    print("Backend did not become available in time.")
    return False


def run_simulation(
    backend_url: str,
    bus_id: str,
    speed: float,
    duration_minutes: float,
    route: List[Dict[str, float]],
):
    """Run the simulation."""
    print(f"\n{'='*60}")
    print(f"PM Detection Simulator")
    print(f"{'='*60}")
    print(f"Backend URL: {backend_url}")
    print(f"Bus ID: {bus_id}")
    print(f"Speed: {speed}x")
    print(f"Duration: {duration_minutes} minutes")
    print(f"Route points: {len(route)}")
    print(f"{'='*60}\n")
    
    session = create_session_with_retry()
    
    # Calculate frames (assume 1 frame per second of simulation time)
    total_frames = int(duration_minutes * 60)
    frame_interval = 1.0 / speed  # Real-world seconds between frames
    
    start_time = datetime.now(timezone.utc)
    events_sent = 0
    events_new = 0
    events_updated = 0
    
    print(f"Starting simulation with {total_frames} frames...")
    print(f"Event zones: {EVENT_ZONES}")
    print()
    
    for frame in range(total_frames):
        # Calculate simulation timestamp
        sim_seconds = frame  # Each frame = 1 second of simulation
        sim_timestamp = datetime.now(timezone.utc)  # Use real current time for demo
        
        # Calculate position along route
        progress = frame / total_frames
        lat, lon = interpolate_position(route, progress)
        
        # Check if we should generate an event
        if should_generate_event(frame, EVENT_ZONES):
            event = create_event(bus_id, lat, lon, sim_timestamp)
            
            print(f"[Frame {frame:4d}] Generating event at ({lat:.4f}, {lon:.4f}) "
                  f"confidence={event['confidence']:.2f}")
            
            result = send_event(session, backend_url, event)
            
            if result:
                events_sent += 1
                kind = result.get("kind", "unknown")
                
                if kind == "new":
                    events_new += 1
                    print(f"           → NEW event created (ID: {result['event']['id'][:8]}...)")
                elif kind == "update":
                    events_updated += 1
                    count = result["event"]["occurrence_count"]
                    print(f"           → UPDATED existing event (count: {count})")
        
        # Sleep for frame interval
        time.sleep(frame_interval)
        
        # Progress indicator every 30 frames
        if frame > 0 and frame % 30 == 0:
            print(f"[Progress] Frame {frame}/{total_frames} "
                  f"({frame/total_frames*100:.0f}%) - "
                  f"Events: {events_new} new, {events_updated} updates")
    
    print()
    print(f"{'='*60}")
    print(f"Simulation Complete!")
    print(f"{'='*60}")
    print(f"Total frames: {total_frames}")
    print(f"Events sent: {events_sent}")
    print(f"  - New events: {events_new}")
    print(f"  - Updates: {events_updated}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="PM Detection Event Simulator"
    )
    parser.add_argument(
        "--bus-id",
        type=str,
        default="bus-1",
        help="Bus ID (default: bus-1)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Simulation speed multiplier (default: 1.0)",
    )
    parser.add_argument(
        "--minutes",
        type=float,
        default=3.0,
        help="Simulation duration in minutes (default: 3)",
    )
    parser.add_argument(
        "--route",
        type=str,
        default=None,
        help="Path to route.json file",
    )
    
    args = parser.parse_args()
    
    # Get backend URL from environment
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    
    # Remove trailing slash
    backend_url = backend_url.rstrip("/")
    
    # Wait for backend
    if not wait_for_backend(backend_url):
        sys.exit(1)
    
    # Load route
    if args.route:
        route_path = Path(args.route)
    else:
        # Check default location
        route_path = Path(__file__).parent / "sample_data" / "route.json"
    
    route = load_route(route_path)
    
    # Run simulation
    try:
        run_simulation(
            backend_url=backend_url,
            bus_id=args.bus_id,
            speed=args.speed,
            duration_minutes=args.minutes,
            route=route,
        )
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
