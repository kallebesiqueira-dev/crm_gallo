"""Landing-page pre-sales chatbot.

Holds the system prompt + product knowledge for the public assistant and a
static, keyword-aware fallback used whenever the AI provider is disabled or
unreachable. Knowledge is deliberately conservative (plans, security, how to
start) so the bot never invents commitments. Reuses `chat_completion`, so it
inherits the configured provider (Groq / Mistral / Anthropic / Ollama) and its
fallback chain.
"""

from __future__ import annotations

from app.config import get_settings
from app.logging_setup import get_logger
from app.services.llm import LLMError, Message, chat_completion

log = get_logger(__name__)
settings = get_settings()

SYSTEM_PROMPT = (
    "You are the friendly pre-sales assistant for GALLO CRM (gallo-crm.com), an "
    "AI-native, multilingual SaaS CRM by GALLO CRM S.r.l. (Italy, EU).\n\n"
    "Your job: answer visitor questions about the product and help them get "
    "started. Be concise (2-5 sentences), warm and professional. Reply in the "
    "SAME language as the user's message. Never invent features, prices, or "
    "legal/security guarantees beyond the facts below; if unsure, say so and "
    "point them to support.\n\n"
    "PRODUCT FACTS:\n"
    "- What it is: a CRM to manage leads, customers, deals, tasks and a drag-and-"
    "drop sales pipeline, with a built-in AI copilot (lead scoring, customer "
    "summaries, an assistant) plus quotes, contracts and e-signature.\n"
    "- Languages: 7 fully human-translated (English, Italiano, Deutsch, Français, "
    "Español, Português, Rumantsch).\n"
    "- Plans (per user / month, billed via Stripe): Free €0 (up to 2 users, "
    "forever, no card), Standard €19, Business €39, Premium €59. Premium includes "
    "a 14-day free trial.\n"
    "- Free trial: start on Free with no credit card; Premium adds a 14-day trial.\n"
    "- Security & data: EU data residency, GDPR-aware, encryption in transit and "
    "at rest, immutable audit logs, multi-tenant isolation, optional two-factor "
    "auth. Open source under AGPL-3.0; self-hosting is possible.\n"
    "- How to start: click “Start free” / open the sign-up page — under a "
    "minute, no card for the Free plan.\n"
    "- Support: email gallo-crm@hotmail.com or WhatsApp; Premium adds priority "
    "support.\n\n"
    "If asked something off-topic or that you cannot answer, politely steer back "
    "to GALLO CRM and suggest signing up free or contacting support."
)

# Static fallback used when the AI is off/unreachable. Keyword-aware (matches a
# few language stems) so common questions still get a useful answer; otherwise a
# safe general reply. English by design — a degraded, provider-down state.
_FALLBACK_DEFAULT = (
    "Thanks for your interest in GALLO CRM! Our AI assistant is offline right now, "
    "but here's the gist: it's an AI-native, multilingual CRM (leads, customers, "
    "deals, pipeline, quotes, contracts) with a Free plan for up to 2 users — no "
    "card required. Paid plans start at €19/user/month. Click “Start free” "
    "to begin, see Pricing for plans, or email gallo-crm@hotmail.com for help."
)

_FALLBACK_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("price", "pricing", "plan", "cost", "preç", "prezzo", "preis", "prix", "precio"),
        "GALLO CRM has four plans billed monthly via Stripe: Free €0 (up to 2 "
        "users, forever, no card), Standard €19, Business €39 and Premium "
        "€59 per user/month (Premium adds a 14-day free trial). See the Pricing "
        "page for the full comparison.",
    ),
    (
        ("free", "trial", "gratis", "gratuito", "grátis", "kostenlos", "essai", "prova"),
        "Yes — you can start completely free for up to 2 users, forever, with no "
        "credit card. Premium also offers a 14-day free trial. Click “Start "
        "free” to create your workspace in under a minute.",
    ),
    (
        (
            "security", "secure", "data", "gdpr", "privacy",
            "sicurezza", "dati", "datenschutz", "données",
        ),
        "Security is core: EU data residency, GDPR-aware, encryption in transit and "
        "at rest, immutable audit logs, tenant isolation and optional 2FA. GALLO CRM "
        "is also open source (AGPL-3.0) and self-hostable.",
    ),
    (
        (
            "start", "begin", "sign up", "signup", "register",
            "começ", "iniziare", "anfangen", "commencer", "empezar",
        ),
        "Getting started takes under a minute: click “Start free” / open "
        "the sign-up page, create your account (no card for the Free plan) and "
        "you're in.",
    ),
    (
        ("support", "help", "contact", "suporte", "supporto", "hilfe", "aide", "ayuda"),
        "Happy to help! Reach us at gallo-crm@hotmail.com or via WhatsApp. Premium "
        "plans include priority support.",
    ),
    (
        ("feature", "function", "funcional", "funzional", "funktion", "fonctionnalit"),
        "GALLO CRM covers leads, customers, deals and a drag-and-drop pipeline, plus "
        "an AI copilot (lead scoring, summaries, assistant), quotes, contracts and "
        "e-signature — in 7 languages.",
    ),
]


def static_fallback(message: str) -> str:
    text = (message or "").lower()
    for keywords, answer in _FALLBACK_RULES:
        if any(k in text for k in keywords):
            return answer
    return _FALLBACK_DEFAULT


async def answer_question(
    message: str,
    history: list[tuple[str, str]] | None = None,
    locale: str | None = None,
) -> tuple[str, str]:
    """Answer a visitor question. Returns ``(text, source)`` where source is
    ``"ai"`` or ``"fallback"``. Never raises — always degrades to fallback."""
    message = (message or "").strip()
    if not message:
        return _FALLBACK_DEFAULT, "fallback"

    if not settings.public_chatbot_enabled:
        return static_fallback(message), "fallback"

    messages: list[Message] = []
    for role, content in history or []:
        content = (content or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    system = SYSTEM_PROMPT
    if locale:
        system = f"{system}\n\nThe user's interface language is '{locale}'."

    try:
        answer = await chat_completion(messages, system=system, max_tokens=500)
    except LLMError as e:
        log.info("public_chatbot.fallback", reason=str(e)[:200])
        return static_fallback(message), "fallback"

    answer = (answer or "").strip()
    if not answer:
        return static_fallback(message), "fallback"
    return answer, "ai"
