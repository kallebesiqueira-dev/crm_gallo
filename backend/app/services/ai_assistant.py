import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.models import Customer
from app.services.llm import LLMError, chat_completion, chat_completion_stream, is_configured

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an AI sales assistant inside a CRM platform. "
    "You help sales reps summarize conversations, draft follow-up emails, "
    "analyze deal risk, suggest next steps, and translate messages. "
    "Be concise, action-oriented, and professional."
)


async def chat(
    user_message: str,
    locale: str = "en",
    history: list[dict] | None = None,
) -> str:
    if not is_configured():
        return (
            "AI assistant is not configured. Configure LLM_PROVIDER + ANTHROPIC_API_KEY "
            f"or start the Ollama container to enable AI responses. (locale={locale})"
        )

    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})
    try:
        return await chat_completion(
            messages=messages,
            system=f"{SYSTEM_PROMPT} Reply in locale: {locale}.",
            max_tokens=1024,
        )
    except LLMError as e:
        logger.warning("Assistant LLM failed: %s", e)
        return f"⚠️ AI provider error: {e}"


async def chat_stream(
    user_message: str,
    locale: str = "en",
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming variant of chat() — yields text tokens as they arrive."""
    if not is_configured():
        yield (
            "AI assistant is not configured. Configure LLM_PROVIDER + ANTHROPIC_API_KEY "
            f"or start the Ollama container to enable AI responses. (locale={locale})"
        )
        return

    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})
    try:
        async for chunk in chat_completion_stream(
            messages=messages,
            system=f"{SYSTEM_PROMPT} Reply in locale: {locale}.",
            max_tokens=1024,
        ):
            yield chunk
    except LLMError as e:
        logger.warning("Assistant LLM stream failed: %s", e)
        yield f"⚠️ AI provider error: {e}"


def _heuristic_summary(customer: Customer) -> str:
    bits = [
        f"{customer.first_name} {customer.last_name}",
        customer.company or "",
        customer.industry or "",
        customer.country or "",
    ]
    return "Heuristic summary: " + ", ".join(b for b in bits if b)


async def summarize_customer(
    customer: Customer,
    locale: str = "en",
    open_deals: list[Any] | None = None,
    open_tasks: list[Any] | None = None,
) -> str:
    if not is_configured():
        return _heuristic_summary(customer)

    payload: dict[str, Any] = {
        "name": f"{customer.first_name} {customer.last_name}",
        "company": customer.company,
        "industry": customer.industry,
        "country": customer.country,
        "website": customer.website,
        "notes": customer.notes,
    }
    if open_deals:
        payload["open_deals"] = [
            {
                "title": d.title,
                "value": float(d.value or 0),
                "currency": d.currency.value,
                "stage": d.stage.value,
            }
            for d in open_deals
        ]
    if open_tasks:
        payload["pending_tasks"] = [
            {
                "title": t.title,
                "due_date": str(t.due_date) if t.due_date else None,
                "priority": t.priority.value,
            }
            for t in open_tasks
        ]

    try:
        return await chat_completion(
            messages=[{"role": "user", "content": f"Summarize this customer:\n{payload}"}],
            system=(
                "You write concise CRM customer summaries (2-3 sentences). "
                "Highlight the relationship status, open pipeline value, and "
                "the single most useful next action for the sales rep. "
                f"Write the summary in the user's language (locale code: {locale})."
            ),
            max_tokens=400,
        )
    except LLMError as e:
        logger.warning("Summary LLM failed: %s", e)
        return f"{_heuristic_summary(customer)}\n\n(AI fallback — {e})"
