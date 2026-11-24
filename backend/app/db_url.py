"""Normalize a SQLAlchemy/asyncpg URL and its connect args.

Managed Postgres (Neon, Supabase) speaks TLS and often rejects the
libpq `sslmode` query parameter that asyncpg does not understand.
Poolers also disallow asyncpg's prepared-statement cache.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_SSL_HOSTS = ("supabase.co", "pooler.supabase.com", "neon.tech")


def prepare_async_url(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    query.pop("ssl", None)
    query.pop("channel_binding", None)
    host = (parsed.hostname or "").lower()
    use_ssl = sslmode not in (None, "", "disable") or any(part in host for part in _SSL_HOSTS)
    clean = urlunparse(parsed._replace(query=urlencode(query)))
    args: dict = {"server_settings": {"statement_timeout": "30000"}}
    if use_ssl:
        # "require" encrypts without pinning a CA. The Supabase pooler
        # presents a chain the default trust store rejects as self-signed.
        args["ssl"] = "require"
    if "pooler" in host or host.endswith("neon.tech"):
        args["statement_cache_size"] = 0
    return clean, args
