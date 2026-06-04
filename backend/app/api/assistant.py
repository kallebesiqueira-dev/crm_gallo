from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.config import get_settings
from app.deps import get_current_user
from app.models import User
from app.rate_limit import limiter, user_or_ip_key
from app.services.ai_assistant import chat

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
settings = get_settings()


class AssistantRequest(BaseModel):
    message: str
    locale: str = "en"


class AssistantResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=AssistantResponse)
@limiter.limit(f"{settings.rate_limit_assistant_per_minute}/minute", key_func=user_or_ip_key)
async def chat_with_assistant(
    request: Request,
    payload: AssistantRequest,
    user: User = Depends(get_current_user),
) -> AssistantResponse:
    reply = await chat(payload.message, locale=payload.locale or user.locale)
    return AssistantResponse(reply=reply)
