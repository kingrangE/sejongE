"use client";

import { useRef, useState } from "react";
import SourceCard from "@/components/SourceCard";
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
  clarify: "확인",
  smalltalk: "일반",
};

const EXAMPLES = [
  "지금 신청 가능한 비교과 알려줘",
  "이번 학기 시험 일정 언제야?",
  "자연어처리 하는 연구실 추천해줘",
];

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const sessionId = useRef<string | null>(null);
  const nextId = useRef(0);

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
      await streamChat(q, sessionId.current, {
        onSession: (sid) => (sessionId.current = sid),
        onMeta: (intent) => patch(botId, (m) => ({ ...m, intent })),
        onDelta: (tok) => patch(botId, (m) => ({ ...m, text: m.text + tok })),
        onClarify: (t) => patch(botId, (m) => ({ ...m, intent: "clarify", text: t })),
        onAbstain: (t) => patch(botId, (m) => ({ ...m, text: t })),
        onSources: (s) => patch(botId, (m) => ({ ...m, sources: s })),
        onProfile: setProfile,
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
              {m.text || (m.role === "assistant" && busy ? "…" : "")}
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
        <div className="row">학년: <b>{profile?.grade ?? "-"}</b></div>
        <div className="row">전공: <b>{profile?.major ?? "-"}</b></div>
        <div className="row">관심사: <b>{profile?.interests?.join(", ") || "-"}</b></div>
        <div className="hint">로그인 없이 대화 중 필요한 정보만 받아 맞춤 응답합니다.</div>
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
