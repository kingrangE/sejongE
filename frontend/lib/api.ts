// 백엔드 /chat (POST + SSE) 클라이언트.
// EventSource는 GET만 지원하므로 fetch 스트리밍으로 SSE를 직접 파싱한다.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface Source {
  url: string;
  doc_type: string;
  score: number;
  snippet: string;
  original_ref?: string | null;
}

export interface Profile {
  grade: number | null;
  major: string | null;
  interests: string[];
  asked_fields: string[];
}

export interface ChatHandlers {
  onMeta?: (intent: string) => void;
  onDelta?: (token: string) => void;
  onClarify?: (text: string) => void;
  onAbstain?: (text: string) => void;
  onSources?: (sources: Source[]) => void;
  onProfile?: (profile: Profile) => void;
  onDone?: () => void;
}

export async function streamChat(
  message: string,
  profile: Profile,
  handlers: ChatHandlers,
): Promise<void> {
  // 프로필은 클라이언트가 보관(localStorage)하고 매 요청에 동봉 → 백엔드 무상태.
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, profile }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat 요청 실패: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      dispatch(block, handlers);
    }
  }
}

function dispatch(block: string, h: ChatHandlers): void {
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  const parsed = data ? JSON.parse(data) : null;
  switch (event) {
    case "meta":
      h.onMeta?.(parsed.intent);
      break;
    case "delta":
      h.onDelta?.(parsed as string);
      break;
    case "clarify":
      h.onClarify?.(parsed.text);
      break;
    case "abstain":
      h.onAbstain?.(parsed.text);
      break;
    case "sources":
      h.onSources?.(parsed as Source[]);
      break;
    case "profile":
      h.onProfile?.(parsed as Profile);
      break;
    case "done":
      h.onDone?.();
      break;
  }
}
