"""채팅 엔드포인트 — SSE 스트리밍.

POST /chat {message, session_id?} → text/event-stream
이벤트 순서: session → meta → (clarify | abstain | (sources, delta*)) → profile → done
clarify/abstain은 LLM 없이 즉시 응답(키 불필요).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.api.deps import get_orchestrator, get_session_store
from sejong_rag.api.schemas import ChatRequest
from sejong_rag.api.session import SessionStore
from sejong_rag.models import ConversationProfile

router = APIRouter()


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(
    req: ChatRequest,
    orch: Orchestrator = Depends(get_orchestrator),
    store: SessionStore = Depends(get_session_store),
) -> StreamingResponse:
    session_id, profile = store.get_or_create(req.session_id)

    def event_stream():
        yield _sse("session", {"session_id": session_id})
        for event, data in orch.run_stream(req.message, profile):
            if event == "profile":
                store.set(session_id, ConversationProfile(**data))
            yield _sse(event, data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
