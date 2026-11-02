import json
import logging
import queue
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Manages Server-Sent Event (SSE) listeners for real-time in-store alerts."""

    def __init__(self):
        self.listeners: List[queue.Queue] = []

    def listen(self) -> queue.Queue:
        q = queue.Queue(maxsize=100)
        self.listeners.append(q)
        return q

    def unlisten(self, q: queue.Queue):
        if q in self.listeners:
            self.listeners.remove(q)

    def broadcast(self, event_type: str, data: Dict[str, Any]):
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        dead_listeners = []
        for q in self.listeners:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead_listeners.append(q)
            except Exception:
                dead_listeners.append(q)

        for q in dead_listeners:
            self.unlisten(q)


broadcaster = EventBroadcaster()

