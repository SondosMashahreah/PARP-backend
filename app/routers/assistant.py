from fastapi import APIRouter, HTTPException, status

from app.schemas.assistant import AssistantMessageRequest, AssistantMessageResponse
from app.services.assistant_service import ask_parp_assistant


router = APIRouter(prefix="/api/assistant", tags=["Assistant"])


@router.post("/chat", response_model=AssistantMessageResponse)
def chat_with_assistant(payload: AssistantMessageRequest):
    try:
        answer = ask_parp_assistant(payload.message)
        return AssistantMessageResponse(answer=answer)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Assistant service is currently unavailable.",
        ) from exc
