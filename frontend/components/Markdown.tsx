import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// 채팅 메시지의 마크다운 렌더링(GFM: 표·취소선·링크 자동변환 등).
// 원시 HTML은 렌더하지 않아 XSS에 안전하다.
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
