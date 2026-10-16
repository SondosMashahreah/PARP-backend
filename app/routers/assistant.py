from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.dependencies import security, get_current_user
from app.schemas.assistant import AssistantMessageRequest, AssistantMessageResponse
from app.services.assistant_service import ask_parp_assistant

router=APIRouter(prefix='/api/assistant',tags=['Assistant'])
_lock=Lock()
_calls=defaultdict(deque)

def assistant_actor(request:Request,credentials=Depends(security),db:Session=Depends(get_db)):
    # Missing token = guest. An invalid supplied token MUST fail, never downgrade silently.
    if credentials is None:
        if request.headers.get('authorization'):raise HTTPException(401,'Invalid authentication')
        return None
    return get_current_user(request,credentials,db)

def rate_limit(key):
    now=monotonic()
    with _lock:
        if len(_calls)>4096:
            for old in list(_calls):
                if not _calls[old] or _calls[old][-1]<now-60:del _calls[old]
            if len(_calls)>4096:raise HTTPException(429,'Assistant is busy. Please retry shortly.')
        queue=_calls[key]
        while queue and queue[0]<now-60:queue.popleft()
        if len(queue)>=12:raise HTTPException(429,'Too many requests. Please retry in a minute.')
        queue.append(now)

@router.post('/chat',response_model=AssistantMessageResponse)
def chat_with_assistant(payload:AssistantMessageRequest,request:Request,db:Session=Depends(get_db),user=Depends(assistant_actor)):
    key=f'{user.role}:{user.id}' if user else f'guest:{request.client.host if request.client else "unknown"}'
    rate_limit(key)
    if not payload.message.strip():raise HTTPException(422,'Message cannot be blank')
    try:
        return ask_parp_assistant(db,user,payload)
    except RuntimeError as exc:
        raise HTTPException(503,str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502,'Assistant service is currently unavailable. Please retry.') from exc
