import json
import logging
import re
from datetime import UTC, datetime

from app.models import Lead
from app.services.llm import LLMError, chat_completion, is_configured

logger = logging.getLogger(__name__)

_SCORING_SYSTEM = (
    "You are an expert B2B sales analyst. Respond with ONLY a single JSON object — "
    "no preamble, no code fences, no commentary. Schema:\n"
    '{"score": <int 0-100>, "priority": "low"|"medium"|"high", '
    '"next_action": "<one concrete next step, <=120 chars>", '
    '"conversion_probability": <float 0.0-1.0>, '
    '"risk_analysis": "<2-3 sentences on key risks or blockers>"}'
)


def _serialize_lead(lead: Lead) -> dict:
    return {
        "company": lead.company,
        "industry": lead.industry,
        "country": lead.country,
        "company_size": lead.company_size,
        # `budget` is a Numeric column → Decimal, which `json.dumps` can't
        # serialize. Coerce to float so the prompt carries a plain number
        # (and scoring doesn't crash with TypeError). See `default=str` below
        # as a backstop for any other non-JSON type that creeps in.
        "budget": float(lead.budget) if lead.budget is not None else None,
        "source": lead.source,
        "stage": lead.stage.value,
        "notes": lead.notes,
    }


def _heuristic_score(lead: Lead) -> dict:
    score = 30
    if lead.budget:
        score += min(30, int(lead.budget / 10000))
    if lead.company_size:
        score += min(20, lead.company_size // 50)
    if lead.email:
        score += 5
    if lead.phone:
        score += 5
    if lead.industry:
        score += 5
    if lead.notes:
        score += 5
    score = max(0, min(100, score))
    priority = "high" if score >= 70 else "medium" if score >= 40 else "low"
    return {
        "score": score,
        "priority": priority,
        "next_action": "Reach out via email to qualify need and timeline.",
        "conversion_probability": round(score / 100, 2),
        "risk_analysis": "Heuristic score — configure an LLM provider for AI-powered analysis.",
    }


def _parse_score_json(text: str) -> dict | None:
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    # Try direct parse, otherwise extract first {...} block
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def _validate_score(data: dict) -> dict | None:
    required = {"score", "priority", "next_action", "conversion_probability", "risk_analysis"}
    if not required.issubset(data.keys()):
        return None
    try:
        data["score"] = max(0, min(100, int(data["score"])))
        data["conversion_probability"] = max(0.0, min(1.0, float(data["conversion_probability"])))
        data["priority"] = str(data["priority"]).lower()
        data["next_action"] = str(data["next_action"])[:200]
        data["risk_analysis"] = str(data["risk_analysis"])
    except (TypeError, ValueError):
        return None
    if data["priority"] not in {"low", "medium", "high"}:
        return None
    return data


async def score_lead(lead: Lead, locale: str = "en") -> dict:
    if not is_configured():
        result = _heuristic_score(lead)
        result["scored_at"] = datetime.now(UTC)
        return result

    prompt = f"Lead data:\n{json.dumps(_serialize_lead(lead), default=str)}"
    try:
        text = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system=_SCORING_SYSTEM
            + f" Write the 'next_action' and 'risk_analysis' text in the user's "
            f"language (locale code: {locale}); keep the JSON keys and the "
            f"'priority' value ('low'/'medium'/'high') in English.",
            max_tokens=512,
        )
        parsed = _parse_score_json(text)
        validated = _validate_score(parsed) if parsed else None
        if not validated:
            logger.warning(
                "LLM scoring returned unparseable JSON, using heuristic. Raw: %s",
                text[:200],
            )
            result = _heuristic_score(lead)
            result["risk_analysis"] = "Heuristic fallback — LLM response was not valid JSON."
        else:
            result = validated
    except LLMError as e:
        logger.warning("LLM scoring failed, using heuristic: %s", e)
        result = _heuristic_score(lead)
        result["risk_analysis"] = f"Heuristic fallback — {e}"

    result["scored_at"] = datetime.now(UTC)
    return result
