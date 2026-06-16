"""Dump the FastAPI OpenAPI schema to stdout (stable, sorted).

Single source of truth for the frontend's generated API types
(`frontend/src/lib/api-types.ts` via openapi-typescript). The HTTP
`/openapi.json` route is disabled in production, but `app.openapi()` builds
the schema from the routers regardless — no server or DB needed.

    cd backend && python -m scripts.dump_openapi > openapi.json

CI diffs the regenerated output against the committed `backend/openapi.json`
to catch schema drift; the frontend then diffs its regenerated types against
that file. Keep both in sync by running the generators after schema changes.
"""

from __future__ import annotations

import json

from app.main import app


def main() -> None:
    # sort_keys = stable diffs across runs/machines; ensure_ascii=False keeps
    # any non-ASCII descriptions readable.
    print(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
