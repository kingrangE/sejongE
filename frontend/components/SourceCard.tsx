import type { Source } from "@/lib/api";

const DOC_LABEL: Record<string, string> = {
  bigyogwa: "비교과",
  calendar: "학사일정",
  lab: "연구실",
};

export default function SourceCard({ source, index }: { source: Source; index: number }) {
  return (
    <a className="source-card" href={source.url} target="_blank" rel="noreferrer">
      <span className="source-index">[{index}]</span>
      <span className="source-badge">{DOC_LABEL[source.doc_type] ?? source.doc_type}</span>
      <span className="source-snippet">{source.snippet}</span>
    </a>
  );
}
