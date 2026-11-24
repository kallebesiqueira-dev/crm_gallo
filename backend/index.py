"""Vercel looks for an ASGI `app` next to requirements.txt.

The package is also named `app`, so the entrypoint lives here rather
than in `app.py` (which would shadow the package).
"""

from app.main import app

__all__ = ["app"]
