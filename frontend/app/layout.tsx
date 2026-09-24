import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AskMyDocs — Ask questions about your documents",
  description:
    "Upload PDFs, Word docs, or Markdown files and get cited answers grounded strictly in your own documents. Open source RAG project.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased bg-neutral-950 text-neutral-100">
        {children}
      </body>
    </html>
  );
}
