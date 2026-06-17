"""수동 채점용 덤프 — 골든 질의를 실행해 {질문·의도·답변·출처}를 Markdown으로 출력.

자동 LLM 채점을 쓰지 않고, 사람이 ○/△/✕로 직접 채점하는 방식(설계 결정).
실행:  PYTHONPATH=src python eval/dump_answers.py [골든.json]
필요:  OPENAI_API_KEY, ANTHROPIC_API_KEY, 그리고 색인에 적재된 데이터.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sejong_rag.agent.factory import build_orchestrator  # noqa: E402
from sejong_rag.config import get_settings  # noqa: E402
from sejong_rag.time_utils import now_kst, today_kst  # noqa: E402


def main(argv: list[str]) -> int:
    golden_path = Path(argv[1]) if len(argv) > 1 else Path(__file__).parent / "golden" / "bigyogwa.json"
    queries = json.loads(golden_path.read_text(encoding="utf-8"))

    orch = build_orchestrator()
    rows = []
    for q in queries:
        res = orch.run(q["query"])
        rows.append((q, res))

    lines: list[str] = []
    lines.append("# RAG 수동 채점 리포트")
    lines.append("")
    lines.append(f"- 생성: {now_kst().isoformat()}  (기준일 {today_kst()})")
    lines.append(f"- 골든셋: `{golden_path.name}` ({len(queries)}문항)")
    lines.append("- 채점란에 ○(정답) / △(부분) / ✕(오답)을 직접 기입하세요.")
    lines.append("")
    lines.append("| # | 분류 | 질문 | 유형 | 채점 | 기대 |")
    lines.append("|--:|---|---|---|:--:|---|")
    for i, (q, res) in enumerate(rows, 1):
        lines.append(
            f"| {i} | {q['category']} | {q['query']} | {res.kind} |  | {q.get('expected','')} |"
        )
    lines.append("")
    lines.append("## 상세")
    for i, (q, res) in enumerate(rows, 1):
        lines.append(f"\n### {i}. [{q['category']}] {q['query']}")
        lines.append(f"- 의도: `{res.intent.value}` · 유형: `{res.kind}`")
        lines.append(f"- 기대: {q.get('expected','')}")
        lines.append("")
        lines.append("**답변**")
        lines.append("")
        lines.append("> " + (res.text or "").replace("\n", "\n> "))
        if res.sources:
            lines.append("")
            lines.append("**검색 출처**")
            for j, c in enumerate(res.sources, 1):
                lines.append(f"- [{j}] (score {c.score:.3f}) {c.source_url}")
        lines.append("")

    out = get_settings().data_dir / "eval_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[eval] {len(rows)}문항 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
