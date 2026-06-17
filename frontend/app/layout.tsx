import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "세종대 통합 정보 챗봇",
  description: "학사일정·비교과·연구실 정보를 한 곳에서 묻고 답하는 RAG 챗봇",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
