"""채팅 엔드포인트 — SSE 스트리밍 (무상태).

POST /chat {message, profile?} → text/event-stream
이벤트 순서: meta → (clarify | abstain | (sources, delta*)) → profile → done
프로필은 클라이언트가 보관·전송하고, 서버는 대화에서 추출한 값을 머지해 돌려준다(profile 이벤트).
clarify/abstain은 LLM 없이 즉시 응답(키 불필요).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.api.deps import get_orchestrator
from sejong_rag.api.schemas import ChatRequest
from sejong_rag.models import ConversationProfile

router = APIRouter()


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(
    req: ChatRequest,
    orch: Orchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    profile = req.profile or ConversationProfile()

    def event_stream():
        for event, data in orch.run_stream(req.message, profile):
            yield _sse(event, data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
