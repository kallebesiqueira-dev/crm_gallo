import logging

from app.models import Customer
from app.services.llm import LLMError, chat_completion, is_configured

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an AI sales assistant inside a CRM platform. "
    "You help sales reps summarize conversations, draft follow-up emails, "
    "analyze deal risk, suggest next steps, and translate messages. "
    "Be concise, action-oriented, and professional."
)


async def chat(user_message: str, locale: str = "en") -> str:
    if not is_configured():
        return (
            "AI assistant is not configured. Configure LLM_PROVIDER + ANTHROPIC_API_KEY "
            f"or start the Ollama container to enable AI responses. (locale={locale})"
        )

    try:
        return await chat_completion(
            messages=[{"role": "user", "content": user_message}],
            system=f"{SYSTEM_PROMPT} Reply in locale: {locale}.",
            max_tokens=1024,
        )
    except LLMError as e:
        logger.warning("Assistant LLM failed: %s", e)
        return f"⚠️ AI provider error: {e}"


def _heuristic_summary(customer: Customer) -> str:
    bits = [
        f"{customer.first_name} {customer.last_name}",
        customer.company or "",
        customer.industry or "",
        customer.country or "",
    ]
    return "Heuristic summary: " + ", ".join(b for b in bits if b)


async def summarize_customer(customer: Customer) -> str:
    if not is_configured():
        return _heuristic_summary(customer)

    payload = {
        "name": f"{customer.first_name} {customer.last_name}",
        "company": customer.company,
        "industry": customer.industry,
        "country": customer.country,
        "website": customer.website,
        "notes": customer.notes,
    }
    try:
        return await chat_completion(
            messages=[{"role": "user", "content": f"Summarize this customer:\n{payload}"}],
            system=(
                "You write concise CRM customer summaries (2-3 sentences). "
                "Highlight the relationship status, last known activity, and "
                "the single most useful follow-up action."
            ),
            max_tokens=400,
        )
    except LLMError as e:
        logger.warning("Summary LLM failed: %s", e)
        return f"{_heuristic_summary(customer)}\n\n(AI fallback — {e})"
