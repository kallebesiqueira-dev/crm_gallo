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

from fastapi import Request
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


def user_or_ip_key(request: Request) -> str:
    """Per-user rate-limit bucket, falling back to client IP.

    The IP-based default (`get_remote_address`) is right for pre-auth
    endpoints (login/register) but wrong for authenticated, cost-bearing
    routes like LLM scoring: a whole office behind one NAT would share a
    single bucket. This keys on the JWT `sub` (the user id) read from the
    same access-token cookie / Bearer header `get_current_user` uses, so
    the cap is genuinely per-user. Falls back to IP when no/invalid token
    is present (the route's own auth dep will reject it anyway).

    Imports are local to dodge an import-time cycle (security/cookies pull
    config, which this module also imports).
    """
    from app.cookies import ACCESS_TOKEN_COOKIE
    from app.security import decode_token

    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[len("Bearer ") :]
    if token:
        try:
            sub = decode_token(token).get("sub")
            if sub:
                return f"user:{sub}"
        except ValueError:
            pass
    return f"ip:{get_remote_address(request)}"
