import logging
import time
from typing import Dict, Tuple
from redis import Redis

from app.core.config import Config

logger = logging.getLogger(__name__)


class PresenceService:
    def __init__(self):
        self.cooldown_seconds = getattr(Config, "VIP_COOLDOWN_MINUTES", 30) * 60
        self._redis_client = None
        self._in_memory_cooldown: Dict[str, float] = {}

    @property
    def redis(self):
        if self._redis_client is None:
            try:
                self._redis_client = Redis.from_url(
                    Config.REDIS_URL,
                    socket_connect_timeout=2.0,
                    decode_responses=True,
                )
                self._redis_client.ping()
            except Exception as exc:
                logger.warning("Redis not available for VIP cooldown (%s); using in-memory cache.", exc)
                self._redis_client = False
        return self._redis_client if self._redis_client is not False else None

    def register_detection(self, customer_id: str, camera_id: str = "default") -> Tuple[bool, float]:
        """
        Determines whether an alert should be raised for this customer.
        Returns (should_alert: bool, last_seen_seconds_ago: float).
        If should_alert is True, refreshes the cooldown timer.
        """
        now = time.time()
        cache_key = f"vip_cooldown:{customer_id}"

        # 1. Try Redis
        client = self.redis
        if client:
            try:
                last_seen_str = client.get(cache_key)
                if last_seen_str:
                    last_seen = float(last_seen_str)
                    return False, round(now - last_seen, 1)

                # Set new cooldown
                client.set(cache_key, str(now), ex=self.cooldown_seconds)
                return True, 0.0
            except Exception as exc:
                logger.error("Redis error checking cooldown: %s, falling back to memory", exc)

        # 2. In-memory fallback
        last_seen = self._in_memory_cooldown.get(customer_id)
        if last_seen and (now - last_seen < self.cooldown_seconds):
            return False, round(now - last_seen, 1)

        self._in_memory_cooldown[customer_id] = now
        return True, 0.0

    def reset_cooldown(self, customer_id: str):
        """Allows testing by clearing the cooldown for a customer."""
        client = self.redis
        if client:
            try:
                client.delete(f"vip_cooldown:{customer_id}")
            except Exception:
                pass
        self._in_memory_cooldown.pop(customer_id, None)


presence_service = PresenceService()

