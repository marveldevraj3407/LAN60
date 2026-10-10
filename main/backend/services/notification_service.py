"""Real-time event notification bus with Server-Sent Events (SSE) support."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Dict, Generator, List

logger = logging.getLogger("NotificationBus")


class NotificationBus:
    """Pub/Sub event broadcaster for real-time frontend updates."""

    def __init__(self) -> None:
        self._listeners: List[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        """Register a new SSE client subscriber."""
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a disconnected client subscriber."""
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast an event to all connected listeners."""
        data = {"event": event_type, "data": payload, "timestamp": time.time()}
        with self._lock:
            dead_queues = []
            for q in self._listeners:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    dead_queues.append(q)
            for dq in dead_queues:
                if dq in self._listeners:
                    self._listeners.remove(dq)

    def sse_stream(self, client_queue: queue.Queue) -> Generator[str, None, None]:
        """Yield Server-Sent Events stream formatted strings."""
        try:
            # Send initial ping
            yield f"data: {json.dumps({'event': 'PING', 'data': {}})}\n\n"
            while True:
                try:
                    message = client_queue.get(timeout=25.0)
                    yield f"data: {json.dumps(message)}\n\n"
                except queue.Empty:
                    # Keep-alive comment for SSE connection
                    yield ": keepalive\n\n"
        finally:
            self.unsubscribe(client_queue)
