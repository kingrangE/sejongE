"""FastAPI 앱 진입점.

실행: uvicorn sejong_rag.api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sejong_rag.api.routes_chat import router as chat_router

app = FastAPI(title="세종대 통합 정보 RAG 챗봇 API", version="0.1.0")

# 프론트엔드(Next.js dev) 연동을 위한 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
