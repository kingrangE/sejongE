#!/usr/bin/env python3
"""PostToolUse hook for TodoWrite.

Detects when a plan/todo item transitions into the "completed" state and, when it
does, injects an instruction telling Claude to document that just-finished step
using the `portfolio-doc` skill.

Design notes
------------
- TodoWrite fires on *every* todo update, so we must diff against the previous
  state to find the item(s) that *newly* became completed. We persist the set of
  completed-item descriptions per session in a small temp-file cache.
- On the FIRST time we see a session (no cache yet) we only *seed* the state and
  emit nothing. This prevents re-documenting already-done items when a session is
  resumed or when the first TodoWrite already contains completed items.
- The hook must never break TodoWrite: any error -> exit 0 with no output.
"""

import json
import os
import sys
import hashlib
import tempfile

STATE_DIR = os.path.join(tempfile.gettempdir(), "claude_portfolio_todo_state")


def _state_path(session_id: str) -> str:
    safe = hashlib.sha1((session_id or "default").encode("utf-8")).hexdigest()[:16]
    return os.path.join(STATE_DIR, f"{safe}.json")


def _completed_set(todos):
    """Return the set of descriptions of todos currently marked completed."""
    done = set()
    for t in todos or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("status", "")).lower() == "completed":
            desc = t.get("content") or t.get("activeForm") or ""
            if desc:
                done.add(desc.strip())
    return done


def _emit(payload: dict) -> None:
    """Write JSON to stdout as UTF-8 regardless of the platform console codepage.

    On Windows the default stdout encoding is cp949, which would mangle the Korean
    additionalContext; Claude Code reads hook stdout as UTF-8, so we encode ourselves.
    """
    out = json.dumps(payload, ensure_ascii=False)
    sys.stdout.buffer.write(out.encode("utf-8"))
    sys.stdout.buffer.flush()


def main() -> None:
    # Read raw bytes and decode UTF-8 explicitly: stdin's default codec is cp949 on
    # Windows, which throws on the Korean todo contents Claude Code pipes in.
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    data = json.loads(raw)

    if data.get("tool_name") != "TodoWrite":
        return

    todos = (data.get("tool_input") or {}).get("todos") or []
    total = len(todos)
    current_done = _completed_set(todos)

    session_id = data.get("session_id") or "default"
    path = _state_path(session_id)

    # Load previous completed set; None means "never seen this session before".
    previous = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                previous = set(json.load(f))
        except Exception:
            previous = None

    # Persist current state for the next diff.
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(current_done), f, ensure_ascii=False)

    # First sighting of this session -> seed only, do not trigger.
    if previous is None:
        return

    newly_done = sorted(current_done - previous)
    done_count = len(current_done)
    # "Plan 전체 완료" = 이번 업데이트로 모든 todo가 completed가 된 전환 순간.
    # newly_done 조건을 함께 두어, 이미 완료된 상태에서의 무변화 재호출에는 안 뜨게 한다.
    plan_complete = total > 0 and done_count == total and len(newly_done) > 0

    if not newly_done and not plan_complete:
        return

    parts = []

    if newly_done:
        items = "\n".join(f'  - "{d}"' for d in newly_done)
        parts.append(
            "[portfolio-doc 자동 트리거] 방금 Plan 단계가 완료 상태로 전환되었습니다 "
            f"(진행: {done_count}/{total} 완료).\n"
            "새로 완료된 단계:\n"
            f"{items}\n\n"
            "다음 작업을 계속하기 전에 `portfolio-doc` 스킬을 사용해, 위에서 새로 완료된 "
            "각 단계에 대한 포트폴리오 기술 문서를 작성/갱신하세요. 스킬의 섹션 구조"
            "(적용 이유 · 설계 고민 · 대안과 비교 · 기술 설명)를 따르고, 단계별 파일과 "
            "docs/portfolio/README.md 인덱스를 모두 업데이트하세요."
        )

    if plan_complete:
        parts.append(
            "[project-readme 자동 트리거] 이번 Plan의 모든 단계가 완료되었습니다 "
            f"({done_count}/{total}). 위 단계 문서화를 마친 뒤, 이어서 `project-readme` "
            "스킬로 프로젝트 루트 README.md를 갱신하세요. 핵심 규칙: ① AI가 작성한 티가 "
            "나지 않게(템플릿식 과장·이모지 남발·마케팅 문구 금지), ② 실제 코드에 들어간 "
            "기술 스택이 드러나게, ③ '무엇을 고려해 이렇게 설계했고 그래서 이렇게 개발했다'는 "
            "의사결정 흐름이 보이게, ④ 각 개발 단계를 실무적으로 상세히 서술하세요. "
            "docs/portfolio/ 의 단계 문서들을 1차 근거로 활용하세요."
        )
        parts.append(
            "[commit 자동 트리거] README 갱신까지 마쳤으면, 마지막으로 `commit` 스킬로 "
            "이번 Plan의 변경사항을 커밋하세요. 규칙: Conventional Commits 형식, 한글 "
            "메시지(요약·본문), 그리고 기능 단위로 나눠 각각 별도 커밋. 문서 변경"
            "(docs/portfolio/, README.md)도 관련 커밋 또는 docs 커밋에 포함하세요. "
            "푸시는 사용자가 요청할 때만 합니다."
        )

    _emit({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n\n".join(parts),
        }
    })


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never let a hook failure interfere with TodoWrite.
        sys.exit(0)
