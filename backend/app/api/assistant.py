import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.deps import get_current_user
from app.models import User
from app.rate_limit import limiter, user_or_ip_key
from app.services.ai_assistant import chat, chat_stream

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
settings = get_settings()


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AssistantRequest(BaseModel):
    message: str
    locale: str = "en"
    history: list[ChatMessage] = []


class AssistantResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=AssistantResponse)
@limiter.limit(f"{settings.rate_limit_assistant_per_minute}/minute", key_func=user_or_ip_key)
async def chat_with_assistant(
    request: Request,
    payload: AssistantRequest,
    user: User = Depends(get_current_user),
) -> AssistantResponse:
    prior = [{"role": m.role, "content": m.content} for m in payload.history]
    reply = await chat(payload.message, locale=payload.locale or user.locale, history=prior)
    return AssistantResponse(reply=reply)


@router.post("/chat/stream")
@limiter.limit(f"{settings.rate_limit_assistant_per_minute}/minute", key_func=user_or_ip_key)
async def chat_stream_endpoint(
    request: Request,
    payload: AssistantRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE streaming endpoint — yields `data: {"token": "..."}` lines.
    Ends with `data: [DONE]`. Errors are sent as `data: {"error": "..."}` then DONE."""
    prior = [{"role": m.role, "content": m.content} for m in payload.history]

    async def generate():
        try:
            async for chunk in chat_stream(
                payload.message,
                locale=payload.locale or user.locale,
                history=prior,
            ):
                yield f"data: {json.dumps({'token': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
