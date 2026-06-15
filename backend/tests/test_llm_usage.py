"""Per-org LLM usage tracking — capture buffer + /api/llm-usage/summary.

The capture buffer is pure (no DB). The summary endpoint is exercised over
HTTP with rows seeded through the owner-role `db` session; RLS scopes the
read to the caller's org.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import llm

# ---------- capture buffer (pure) ----------


def test_capture_usage_collects_then_resets():
    with llm.capture_usage() as buf:
        llm._record_usage("ollama", "m", 10, 20)
        llm._record_usage("openai_compat", "gpt", 1, 2)
    assert len(buf) == 2
    assert buf[0] == {"provider": "ollama", "model": "m", "input_tokens": 10, "output_tokens": 20}
    # Outside the block there is no active buffer — recording is a silent no-op.
    llm._record_usage("ollama", "m", 99, 99)
    assert len(buf) == 2


def test_capture_usage_coerces_none_to_zero():
    with llm.capture_usage() as buf:
        llm._record_usage("ollama", "m", None, None)  # type: ignore[arg-type]
    assert buf[0]["input_tokens"] == 0 and buf[0]["output_tokens"] == 0


# ---------- /api/llm-usage/summary ----------


def _seed(db: Session, org_id, use_case: str, inp: int, out: int, *, days_ago: int = 0):
    db.execute(
        text(
            "INSERT INTO llm_usage "
            "(id, organization_id, use_case, provider, model, input_tokens, output_tokens, created_at) "
            "VALUES (gen_random_uuid(), :o, :u, 'ollama', 'm', :i, :ot, "
            "now() - make_interval(days => :d))"
        ),
        {"o": org_id, "u": use_case, "i": inp, "ot": out, "d": days_ago},
    )


def test_summary_requires_auth(client):
    assert client.get("/api/llm-usage/summary").status_code == 401


def test_summary_non_admin_403(other_client):
    # sales_agent is below admin/manager → blocked during dep resolution.
    assert other_client.get("/api/llm-usage/summary").status_code == 403


def test_summary_aggregates_by_use_case(admin_client, test_org, db: Session):
    _seed(db, test_org.id, "lead_scoring", 10, 20)
    _seed(db, test_org.id, "lead_scoring", 5, 5)
    _seed(db, test_org.id, "customer_summary", 3, 7)
    db.commit()

    body = admin_client.get("/api/llm-usage/summary").json()
    assert body["total_calls"] == 3
    assert body["total_input_tokens"] == 18
    assert body["total_output_tokens"] == 32
    stats = {s["use_case"]: s for s in body["by_use_case"]}
    assert stats["lead_scoring"]["calls"] == 2
    assert stats["lead_scoring"]["input_tokens"] == 15
    assert stats["lead_scoring"]["output_tokens"] == 25
    assert stats["customer_summary"]["calls"] == 1


def test_summary_scoped_to_org(admin_client, test_org, other_org, db: Session):
    _seed(db, test_org.id, "lead_scoring", 10, 10)
    _seed(db, other_org.id, "lead_scoring", 999, 999)  # foreign org
    db.commit()
    body = admin_client.get("/api/llm-usage/summary").json()
    assert body["total_calls"] == 1  # RLS hides the other org's row
    assert body["total_input_tokens"] == 10


def test_summary_window_excludes_old(admin_client, test_org, db: Session):
    _seed(db, test_org.id, "lead_scoring", 10, 10, days_ago=60)
    db.commit()
    # Default 30d window excludes the 60-day-old row; widening to 90d includes it.
    assert admin_client.get("/api/llm-usage/summary").json()["total_calls"] == 0
    assert admin_client.get("/api/llm-usage/summary?window_days=90").json()["total_calls"] == 1


def test_summary_empty_org_is_all_zero(admin_client):
    # A fresh org with no usage → all-zero summary, not an error.
    body = admin_client.get("/api/llm-usage/summary?window_days=1").json()
    assert body["total_calls"] == 0
    assert body["by_use_case"] == []
