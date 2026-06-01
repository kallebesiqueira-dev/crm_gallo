"""Background job worker.

We use Arq (async-native, Redis-backed). Same Redis the rest of the
app already uses for sessions/refresh tokens — no extra dep. Arq's
runtime model is one Python process per worker container, pulling
jobs off a single Redis list and dispatching to coroutines.

Submodules:
  * `settings.py` — `WorkerSettings` class consumed by the `arq` CLI
    entrypoint (`arq app.worker.settings.WorkerSettings`).
  * `queue.py`    — `enqueue()` helper called from HTTP handlers.
  * `jobs.py`     — actual coroutines arq dispatches.

Idempotency convention: every job that mutates writes a Redis key
like `job:done:{type}:{id}` with a 24h TTL inside the job body. The
enqueue helper checks the key BEFORE enqueueing (`SETNX`) so
double-clicks / retries don't fan-out to duplicate work. Real
exactly-once semantics need a DB-backed outbox; this is one-best-
effort de-dupe.
"""
