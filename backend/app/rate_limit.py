"""Redis-backed SlowAPI limiter — TD-15.

In-memory counters are wrong as soon as we run more than one
backend replica: each pod sees only its own bucket, so the
effective rate is `N_replicas x configured_limit`. Redis storage
puts the bucket in one place all replicas read/write.

`in_memory_fallback_enabled=True` keeps the service alive if
Redis disappears at runtime — each replica falls back to its own
counter (the old behaviour, degraded). Better than refusing every
request when the dependency is down.

`storage_uri` reuses our existing `REDIS_URL` so there's only one
Redis to point at. `key_prefix` namespaces our buckets so they
don't collide with the refresh-token store / session metadata.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=_settings.redis_url,
    key_prefix="rl:",
    in_memory_fallback_enabled=True,
    in_memory_fallback=[],
)
