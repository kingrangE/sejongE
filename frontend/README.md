# 프론트엔드 (Next.js + React)

세종대 통합 정보 챗봇의 웹 UI. 백엔드 FastAPI(`/chat`, SSE 스트리밍)에 연결한다.

## 실행
백엔드를 먼저 띄운다(다른 터미널):
```bash
cd ../backend
PYTHONPATH=src uvicorn sejong_rag.api.main:app --port 8000
```
프론트엔드:
```bash
npm install
npm run dev          # http://localhost:3000
```
백엔드 주소가 다르면 `NEXT_PUBLIC_API_BASE`로 지정(기본 `http://localhost:8000`).

## 구성
```
app/
  page.tsx       # 채팅 화면(메시지·되묻기·출처·프로필 패널), 스트리밍 표시
  layout.tsx · globals.css
components/
  SourceCard.tsx # 출처 카드(도메인 배지 + 링크)
lib/
  api.ts         # POST /chat 의 SSE를 fetch 스트리밍으로 파싱(EventSource는 GET만 지원)
```

## 동작
한 번의 질문에 대해 백엔드가 SSE 이벤트를 순서대로 흘려보낸다:
`meta(의도) → (clarify | abstain | sources + delta 토큰 스트림) → profile → done`.
- 답변은 토큰 단위로 실시간 출력되고, 근거 출처는 카드로 표시된다.
- 학년/전공/관심사는 우측 패널에서 직접 편집하거나 대화 중 자동 추출되며, **브라우저(localStorage)에
  저장되어 매 요청에 동봉**된다(로그인 없음, 백엔드 무상태 → 사용자 간 충돌 없음).
