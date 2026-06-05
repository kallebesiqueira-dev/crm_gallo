"""Public (unauthenticated) API surface — landing-page chatbot.

Every endpoint here is rate-limited per IP, input-sanitised by Pydantic, and
degrades to a safe static answer instead of erroring, so the marketing site
keeps working with the AI turned off or unreachable. No secrets are returned.
"""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.rate_limit import limiter
from app.services.chatbot import answer_question

settings = get_settings()
router = APIRouter(prefix="/api/public", tags=["public"])

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 8


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatbotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    # Short rolling context. Capped server-side regardless of what's sent.
    history: list[ChatTurn] | None = Field(default=None, max_length=MAX_HISTORY_TURNS * 2)
    locale: str | None = Field(default=None, max_length=8)


class ChatbotResponse(BaseModel):
    message: str
    source: Literal["ai", "fallback"]


@router.post("/chatbot", response_model=ChatbotResponse)
@limiter.limit(f"{settings.rate_limit_chatbot_per_minute}/minute")
async def chatbot(request: Request, payload: ChatbotRequest) -> ChatbotResponse:
    """Landing-page pre-sales assistant. Public + per-IP rate-limited.

    `request` is required by the SlowAPI limiter. Input is sanitised (trim +
    length caps from the schema); the answer never echoes secrets and always
    falls back to a static professional reply on AI failure.
    """
    history = [
        (turn.role, turn.content.strip())
        for turn in (payload.history or [])
        if turn.content.strip()
    ][-MAX_HISTORY_TURNS:]
    text, source = await answer_question(payload.message, history, payload.locale)
    return ChatbotResponse(message=text, source=source)
