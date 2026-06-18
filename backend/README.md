# 세종대 통합 RAG 챗봇 — 백엔드

여러 세종대 사이트 정보를 크롤링·정규화해 한국어로 답하는 RAG 챗봇 백엔드.
세 시나리오 통합: **연구실 추천 / 학사일정 Q&A / 비교과 자격 안내**.

전체 설계: `../` 상위의 계획 문서 참고. 실행 플랫폼은 **macOS / Linux**.

## 요구사항
- Python 3.11+
- `OPENAI_API_KEY` — 임베딩 + 답변 생성 모두 OpenAI (`.env`). Anthropic은 선택.

## 설치
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # 코어 + 개발
# pip install -e ".[dev,hybrid,ocr]"   # v2 하이브리드 / OCR 폴백까지
playwright install chromium      # 동적 페이지 크롤용
cp .env.example .env             # 키 채우기
```

## 테스트
```bash
PYTHONPATH=src pytest -q
```

## 실행 (비교과 크롤)
```bash
# 적재 없이 파싱 결과만 (API 키 불필요)
PYTHONPATH=src python -m sejong_rag.cli crawl --site bigyogwa --dry-run
# 실제 적재 (OpenAI 임베딩 + Chroma, .env 키 필요)
PYTHONPATH=src python -m sejong_rag.cli crawl --site bigyogwa
PYTHONPATH=src python -m sejong_rag.cli crawl --site calendar   # 학사일정
PYTHONPATH=src python -m sejong_rag.cli crawl --site labs       # 연구실(AI융합대학)
PYTHONPATH=src python -m sejong_rag.cli crawl --site all        # 세 도메인 일괄
```

## 지속 운영 (스케줄러)
도메인별 주기로 자동 크롤(비교과 4h·학사일정 1일·연구실 1주). 한 사이트 실패는 격리되어
`data/dead_letter.log`에 기록된다.
```bash
PYTHONPATH=src python -m sejong_rag.cli schedule --run-now   # 초기 1회 적재 후 주기 시작
```

## 수집 점검 (사이트와 대조)
크롤이 잘 되는지 사람이 검수하는 Markdown 리포트 생성 (API 키 불필요):
```bash
# 라이브 파싱 결과로 리포트 → data/inspect_bigyogwa.md
PYTHONPATH=src python -m sejong_rag.cli inspect --site bigyogwa
# 이미 적재된 SQLite 활성 문서로 리포트
PYTHONPATH=src python -m sejong_rag.cli inspect --site bigyogwa --from-store
```
리포트에는 프로그램별 신청기간·상태(오늘 기준 접수중/예정/마감)·모집현황·마일리지·**원본 링크**·임베딩 텍스트가 표로 정리되어, 실제 사이트와 항목을 1:1 대조할 수 있다.

## 질의 (Vector RAG + 되묻기)
적재된 색인에 대해 질문 (OpenAI + Chroma, `OPENAI_API_KEY` 필요):
```bash
PYTHONPATH=src python -m sejong_rag.cli ask --query "지금 신청 가능한 비교과 알려줘"
PYTHONPATH=src python -m sejong_rag.cli ask --query "연구실 추천해줘"   # 관심사 되묻기
PYTHONPATH=src python -m sejong_rag.cli ask --hybrid --query "신입생 멘토링 신청기간"  # v2 BM25+RRF
```
- 질의 의도를 분류하고(비교과/학사일정/연구실), "지금"·"이번 주" 같은 표현과 학년/전공을 **하드 필터**로 변환해 검색한 뒤, 검색 자료만 근거로 출처를 인용해 답한다.
- 정보를 못 찾으면 환각 대신 "없음"으로 답하고, 모호하면 한 가지만 되묻는다.

## 수동 채점 (평가)
골든 질의를 실행해 채점용 Markdown 리포트 생성 (키 필요):
```bash
PYTHONPATH=src python eval/dump_answers.py        # → data/eval_report.md
```
질문·의도·답변·검색 출처가 표로 나오며, 사람이 ○/△/✕로 직접 채점한다.

## API 서버 (FastAPI + SSE)
```bash
PYTHONPATH=src uvicorn sejong_rag.api.main:app --port 8000
# POST /chat {message, profile?} → text/event-stream
#   meta → (clarify | abstain | sources + delta*) → profile → done
# 무상태: 프로필은 클라이언트(localStorage)가 보관·전송, 서버는 추출값을 머지해 돌려줌
```
프론트엔드(Next.js)는 `../frontend` 참고.

## 구조
```
src/sejong_rag/
  config.py        # pydantic-settings (.env), 경로/모델/크롤 설정
  models.py        # LabDoc/CalendarEvent/BigyogwaProgram, ConversationProfile, ContentUnit, Candidate
  time_utils.py    # KST, epoch-day, 한국어 상대날짜 해석("이번 주" 등)
  ingest/
    http_fetcher.py     # httpx 정적 fetch/post + 원본 캐시 + 정중한 지연
    pipeline.py         # 사이트별 ETL 실행(CLI·스케줄러 공용) + dead-letter
    scheduler.py        # APScheduler 도메인별 주기 크롤
    sites/bigyogwa.py   # 비교과 목록 파서 + crawl 러너
    sites/calendar.py   # 학사일정(공개 페이지) 파서
    sites/labs.py       # 연구실/교수(공개 API) 파서 — AI융합대학
  normalize/
    html_clean.py  # 인코딩 감지(cp949/euc-kr)·NFC·본문 텍스트
    dedup.py       # 안정 id·content_hash (멱등/변경감지)
    chunker.py     # 긴 텍스트 청킹
  index/
    store.py       # SQLite 진실원천: 변경분류·소프트삭제·run_ledger
    build_index.py # Transform→Load 멱등 오케스트레이션 (NEW/CHANGED만 임베딩)
    embedder.py    # OpenAI 임베딩 (지연 import)
    vectorstore.py # Chroma 래퍼 (지연 import)
  retrieve/
    retriever.py   # Retriever 인터페이스 + RetrievalFilter (Vector↔Hybrid 교체 지점)
    vector.py      # VectorRetriever(v1) — OpenAI dense + 하드필터
    hybrid.py · bm25.py · tokenize.py  # v2 하이브리드(BM25+RRF, 키위 선택)
    filters.py     # RetrievalFilter → Chroma where / 파이썬 술어 + 메타데이터 투영
    router.py      # 의도 분류 + 시간/자격 필터 추출(결정론)
  agent/
    orchestrator.py # 라우팅→되묻기→검색→근거 기반 생성(+ SSE용 run_stream)
    profile.py      # 프로필 추출 + 되묻기 게이트
    prompts.py      # 시스템 프롬프트(anti-hallucination·인용) + 컨텍스트 포매팅
    llm.py          # OpenAI 챗 래퍼(generate/stream) + LLMClient 인터페이스
    factory.py      # 실제 의존성으로 Orchestrator 조립
  api/
    main.py         # FastAPI 앱(+CORS, /health)
    routes_chat.py  # POST /chat — SSE 스트리밍(무상태: 프로필을 요청에서 받음)
    deps.py · schemas.py
  report.py · cli.py   # 검수 리포트 / CLI(crawl·inspect·ask)
eval/
  golden/bigyogwa.json # 수동 채점용 골든 질의
  dump_answers.py      # 채점 리포트 생성
```

## 단계
- [x] **Phase 0** — 스캐폴드·핵심 모델·시간 유틸·SQLite 저장소·인터페이스
- [x] **Phase 1** — 비교과 ETL 한 줄기(Extract→Transform→Load, 멱등) + 메타필터 + 상태 재계산. 라이브 검증.
  - ⚠️ 알려진 제약: 두드림은 JS SPA라 **정적 fetch는 첫 묶음(~8건)만** 수집. **전체 목록 페이지네이션·상세 본문·자격(학년/전공) 정밀추출은 Playwright 후속** 필요(현재 자격은 전체로 가정). 콘텐츠 유형별(table/image) 추출기도 상세 단계에서 추가.
- [x] **Phase 2** — Vector RAG + 클라리피케이션. 의도 라우팅·하드필터·되묻기·근거 기반 생성·abstention. 결정론 부분 테스트 완료(LLM 생성은 키 필요).
- [x] **Phase 3** — 학사일정(공개 페이지)·연구실(공개 API, AI융합대학 12개 학과 190명) 수집. 세 도메인 모두 동일 ETL·검색 골격 재사용.
- [x] **Phase 4** — FastAPI `/chat` SSE 스트리밍(무상태), Next.js/React 챗 UI(스트리밍·출처 카드·**편집 가능 프로필 패널**, localStorage 보관).
- [x] **Phase 5** — 지속 운영(APScheduler 주기 크롤·dead-letter) + 하이브리드 검색 v2(BM25+RRF, drop-in).

## 테스트 현황
80개 통과: 위 항목 + 스케줄러/파이프라인(장애 격리)·하이브리드(BM25·RRF·필터 술어).
