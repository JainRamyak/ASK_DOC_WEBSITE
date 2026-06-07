import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AskMyDocs — RAG Document Q&A",
  description:
    "Upload any document and ask questions in plain English. Get cited answers powered by RAG — FastAPI, ChromaDB, Gemini, Next.js.",
  keywords: ["RAG", "document QA", "AI", "FastAPI", "ChromaDB", "Gemini"],
  openGraph: {
    title: "AskMyDocs — Ask questions, get cited answers",
    description:
      "Upload a PDF, TXT, DOCX or Markdown file and get grounded, cited answers powered by a full RAG pipeline.",
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "AskMyDocs — RAG Document Q&A",
    description: "Upload any document. Ask anything. Get cited answers.",
  },
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"
  ),
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}