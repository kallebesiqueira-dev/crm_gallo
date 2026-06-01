from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import get_current_user
from app.models import User
from app.services.ai_assistant import chat

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantRequest(BaseModel):
    message: str
    locale: str = "en"


class AssistantResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=AssistantResponse)
async def chat_with_assistant(
    payload: AssistantRequest,
    user: User = Depends(get_current_user),
) -> AssistantResponse:
    reply = await chat(payload.message, locale=payload.locale or user.locale)
    return AssistantResponse(reply=reply)
