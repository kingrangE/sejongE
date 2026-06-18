"use client";

import { useEffect, useRef, useState } from "react";
import SourceCard from "@/components/SourceCard";
import Markdown from "@/components/Markdown";
import { streamChat, type Profile, type Source } from "@/lib/api";

interface Message {
  id: number;
  role: "user" | "assistant";
  intent?: string;
  text: string;
  sources?: Source[];
}

const INTENT_LABEL: Record<string, string> = {
  bigyogwa: "비교과",
  calendar: "학사일정",
  lab: "연구실",
  general: "통합 검색",
  profile: "프로필",
  clarify: "확인",
  smalltalk: "일반",
};

const EXAMPLES = [
  "지금 신청 가능한 비교과 알려줘",
  "이번 학기 시험 일정 언제야?",
  "자연어처리 하는 연구실 추천해줘",
];

const STORAGE_KEY = "sejong_profile_v1";
const EMPTY: Profile = { grade: null, major: null, interests: [], asked_fields: [] };

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState<Profile>(EMPTY);
  const [interestsText, setInterestsText] = useState("");
  const nextId = useRef(0);

  // 최초 로드: localStorage에서 프로필 복원(브라우저별 분리 → 유저 간 충돌 없음)
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const p = { ...EMPTY, ...JSON.parse(raw) } as Profile;
        setProfile(p);
        setInterestsText((p.interests ?? []).join(", "));
      }
    } catch {}
  }, []);

  function saveProfile(p: Profile) {
    setProfile(p);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
    } catch {}
  }

  function patch(id: number, fn: (m: Message) => Message) {
    setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));
  }

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);

    const userId = nextId.current++;
    const botId = nextId.current++;
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", text: q },
      { id: botId, role: "assistant", text: "" },
    ]);

    try {
      await streamChat(q, profile, {
        onMeta: (intent) => patch(botId, (m) => ({ ...m, intent })),
        onDelta: (tok) => patch(botId, (m) => ({ ...m, text: m.text + tok })),
        onClarify: (t) => patch(botId, (m) => ({ ...m, intent: "clarify", text: t })),
        onAbstain: (t) => patch(botId, (m) => ({ ...m, text: t })),
        onSources: (s) => patch(botId, (m) => ({ ...m, sources: s })),
        // 대화에서 자동 추출된 학년/전공을 클라이언트 프로필에 머지·저장
        onProfile: (p) => {
          saveProfile(p);
          setInterestsText((p.interests ?? []).join(", "));
        },
      });
    } catch (e) {
      patch(botId, (m) => ({ ...m, text: "오류가 발생했어요. 백엔드(uvicorn)가 실행 중인지 확인해 주세요." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app">
      <section className="chat">
        <div className="chat-header">
          세종대 통합 정보 챗봇 <small>학사일정 · 비교과 · 연구실</small>
        </div>
        <div className="messages">
          {messages.length === 0 && (
            <div className="msg assistant">
              안녕하세요! 학사일정, 비교과 프로그램, 연구실에 대해 물어보세요.
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.role}`}>
              {m.role === "assistant" && m.intent && (
                <div className="intent">{INTENT_LABEL[m.intent] ?? m.intent}</div>
              )}
              {m.text ? (
                <Markdown>{m.text}</Markdown>
              ) : (
                m.role === "assistant" && busy && <span className="typing">…</span>
              )}
              {m.sources && m.sources.length > 0 && (
                <div className="sources">
                  {m.sources.map((s, i) => (
                    <SourceCard key={i} source={s} index={i + 1} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="무엇이든 물어보세요"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()}>
            보내기
          </button>
        </form>
      </section>

      <aside className="panel">
        <h3>내 프로필</h3>
        <label className="field">
          <span>학년</span>
          <select
            value={profile.grade ?? ""}
            onChange={(e) => saveProfile({ ...profile, grade: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">선택 안 함</option>
            <option value="1">1학년</option>
            <option value="2">2학년</option>
            <option value="3">3학년</option>
            <option value="4">4학년</option>
          </select>
        </label>
        <label className="field">
          <span>전공</span>
          <input
            value={profile.major ?? ""}
            placeholder="예: 컴퓨터공학과"
            onChange={(e) => saveProfile({ ...profile, major: e.target.value || null })}
          />
        </label>
        <label className="field">
          <span>관심사</span>
          <input
            value={interestsText}
            placeholder="쉼표로 구분 (예: 인공지능, 로봇)"
            onChange={(e) => {
              setInterestsText(e.target.value);
              saveProfile({
                ...profile,
                interests: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              });
            }}
          />
        </label>
        <button
          className="clear-btn"
          onClick={() => {
            saveProfile(EMPTY);
            setInterestsText("");
          }}
        >
          프로필 초기화
        </button>
        <div className="hint">
          이 정보는 브라우저에만 저장되며(localStorage), 대화 중 말해주셔도 자동 반영됩니다.
        </div>

        <h3 style={{ marginTop: 18 }}>예시 질문</h3>
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => send(ex)} disabled={busy}>
              {ex}
            </button>
          ))}
        </div>
      </aside>
    </main>
  );
}
