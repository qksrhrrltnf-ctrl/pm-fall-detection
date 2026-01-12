"""Real-time event broadcasting via SSE."""

import asyncio
import json
from typing import AsyncGenerator, Dict, Any, Set
from dataclasses import dataclass, field


@dataclass
class SSEBroadcaster:
    """Simple SSE broadcaster using asyncio queues."""
    
    subscribers: Set[asyncio.Queue] = field(default_factory=set)
    
    def subscribe(self) -> asyncio.Queue:
        """Create a new subscription queue."""
        queue: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscription queue."""
        self.subscribers.discard(queue)
    
    def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast message to all subscribers."""
        for queue in self.subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Skip if queue is full (slow consumer)
                pass
    
    async def stream(self, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        """Generate SSE messages from queue."""
        try:
            while True:
                message = await queue.get()
                yield f"data: {json.dumps(message)}\n\n"
        except asyncio.CancelledError:
            pass


# Global broadcaster instance
broadcaster = SSEBroadcaster()


def broadcast_event(kind: str, event_dict: Dict[str, Any]) -> None:
    """Broadcast an event to all SSE subscribers."""
    broadcaster.broadcast({
        "kind": kind,
        "event": event_dict,
    })
