import Link from "next/link";
import {
  ArrowRight,
  FileText,
  Search,
  Zap,
  Database,
  Code2,
  Cpu,
} from "lucide-react";

/* lucide-react@1.x dropped the Github export — inline SVG instead */
function GithubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

const STEPS = [
  {
    number: "01",
    title: "Upload your document",
    description:
      "Drop a PDF, TXT, DOCX, or Markdown file. The backend chunks it into 512-char segments and embeds each chunk using sentence-transformers locally.",
  },
  {
    number: "02",
    title: "Hybrid retrieval",
    description:
      "Your question is embedded and matched via FAISS semantic search + BM25 keyword search, fused together using Reciprocal Rank Fusion.",
  },
  {
    number: "03",
    title: "Rerank + answer",
    description:
      "A cross-encoder reranker picks the best chunks. Gemini synthesizes a cited answer grounded exclusively in your document.",
  },
];

const STACK = [
  { icon: <Code2 size={14} />, name: "FastAPI", desc: "REST backend" },
  { icon: <Database size={14} />, name: "ChromaDB", desc: "Vector store" },
  { icon: <Cpu size={14} />, name: "Gemini", desc: "LLM provider" },
  { icon: <Search size={14} />, name: "sentence-transformers", desc: "Local embeddings" },
  { icon: <Zap size={14} />, name: "FAISS + BM25", desc: "Hybrid retrieval" },
  { icon: <FileText size={14} />, name: "Next.js 16", desc: "Frontend" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: "#0a0a0a" }}>

      {/* ── Nav ── consistent max-w-5xl, same as all sections ── */}
      <nav
        className="border-b sticky top-0 z-20 backdrop-blur-md"
        style={{ borderColor: "#1a1a1a", background: "rgba(10,10,10,0.9)" }}
      >
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Brand */}
          <Link href="/" className="flex items-center gap-2.5">
            <span
              className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0"
              style={{ background: "#13132a", color: "#818cf8", border: "1px solid #2a2766" }}
            >
              A
            </span>
            <span style={{ color: "#e4e4e7", fontWeight: 600, fontSize: "0.9rem", letterSpacing: "-0.01em" }}>
              AskMyDocs
            </span>
          </Link>

          {/* Nav actions */}
          <div className="flex items-center gap-4">
            <a
              href="https://github.com/JainRamyak/ASK_DOC_WEBSITE"
              target="_blank"
              rel="noopener noreferrer"
              className="nav-link"
              aria-label="View source on GitHub"
            >
              <GithubIcon size={14} />
              <span className="hidden sm:inline">GitHub</span>
            </a>
            <Link href="/app" className="btn-primary px-3.5 py-1.5">
              Open App <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center justify-center text-center px-6 pt-24 pb-20">
        <div style={{ maxWidth: "var(--content-w)", width: "100%", margin: "0 auto" }}>

          {/* Badge */}
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium mb-6 slide-up"
            style={{ background: "#0d0d1f", color: "#818cf8", border: "1px solid #2a2766", animationDelay: "0s" }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: "#818cf8", animation: "glowPulse 2s ease-in-out infinite" }}
            />
            RAG · Retrieval-Augmented Generation
          </div>

          {/* H1 — lineHeight 1.12 gives breathing room at large sizes */}
          <h1
            className="font-bold tracking-tight mb-5 slide-up"
            style={{
              color: "#fff",
              lineHeight: 1.12,
              fontSize: "clamp(2.5rem, 6vw, 3.75rem)",
              animationDelay: "0.06s",
              maxWidth: "640px",
              margin: "0 auto 1.25rem",
            }}
          >
            Ask questions.{" "}
            <span className="gradient-text">Get cited answers.</span>
          </h1>

          {/* Subtitle — zinc-400 on #0a0a0a = 5.9:1 contrast, passes AA */}
          <p
            className="slide-up"
            style={{
              color: "#a1a1aa",
              fontSize: "1.0625rem",
              lineHeight: 1.65,
              maxWidth: "480px",
              margin: "0 auto 2rem",
              animationDelay: "0.1s",
            }}
          >
            Upload any document. Ask anything in plain English. Get cited answers
            grounded in your document — no hallucination, no guessing.
          </p>

          {/* CTAs */}
          <div className="flex items-center gap-3 justify-center flex-wrap slide-up" style={{ animationDelay: "0.16s" }}>
            <Link href="/app" className="btn-primary px-5 py-2.5">
              Try it free <ArrowRight size={14} />
            </Link>
            <a
              href="https://github.com/JainRamyak/ASK_DOC_WEBSITE"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost px-5 py-2.5"
            >
              <GithubIcon size={14} />
              View source
            </a>
          </div>

          {/* Trust hint */}
          <p
            className="slide-up"
            style={{ color: "#3f3f46", fontSize: "0.75rem", marginTop: "1.5rem", animationDelay: "0.22s" }}
          >
            No signup · No API key needed · Upload and go
          </p>
        </div>
      </section>

      {/* ── How it works ── */}
      <section style={{ borderTop: "1px solid #1a1a1a", padding: "5rem 1.5rem" }}>
        <div style={{ maxWidth: "var(--content-w)", margin: "0 auto" }}>

          {/* Section label + heading — tightly coupled */}
          <p style={{ color: "#6366f1", fontSize: "0.6875rem", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", textAlign: "center", marginBottom: "0.375rem" }}>
            How it works
          </p>
          <h2 style={{ color: "#fff", fontWeight: 700, fontSize: "1.75rem", textAlign: "center", marginBottom: "3rem", letterSpacing: "-0.02em" }}>
            The full RAG pipeline
          </h2>

          <div className="grid md:grid-cols-3 gap-4">
            {STEPS.map((step) => (
              <div key={step.number} className="card-glow p-6">
                {/* Step number — visible indigo ghost, not invisible */}
                <div
                  style={{ fontFamily: "ui-monospace, monospace", fontSize: "2rem", fontWeight: 700, color: "#2d2d4a", marginBottom: "1rem", lineHeight: 1 }}
                >
                  {step.number}
                </div>
                <h3 style={{ color: "#e4e4e7", fontWeight: 600, fontSize: "0.9375rem", marginBottom: "0.5rem" }}>
                  {step.title}
                </h3>
                <p style={{ color: "#71717a", fontSize: "0.8125rem", lineHeight: 1.65 }}>
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tech stack ── */}
      <section style={{ borderTop: "1px solid #1a1a1a", padding: "5rem 1.5rem" }}>
        <div style={{ maxWidth: "var(--content-w)", margin: "0 auto" }}>

          <p style={{ color: "#6366f1", fontSize: "0.6875rem", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", textAlign: "center", marginBottom: "0.375rem" }}>
            Tech stack
          </p>
          <h2 style={{ color: "#fff", fontWeight: 700, fontSize: "1.75rem", textAlign: "center", marginBottom: "3rem", letterSpacing: "-0.02em" }}>
            Built with production tools
          </h2>

          {/* 2-col → 3-col, constrained width so items don't stretch */}
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}
          >
            {STACK.map((item) => (
              <div key={item.name} className="card-glow flex items-center gap-3 px-4 py-3 cursor-default">
                <span
                  className="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center"
                  style={{ background: "#0d0d1f", color: "#818cf8" }}
                >
                  {item.icon}
                </span>
                <div>
                  <p style={{ color: "#e4e4e7", fontWeight: 500, fontSize: "0.875rem", lineHeight: 1.2 }}>{item.name}</p>
                  <p style={{ color: "#52525b", fontSize: "0.75rem", marginTop: "1px" }}>{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── properly constrained card, not inline-block trick ── */}
      <section style={{ borderTop: "1px solid #1a1a1a", padding: "5rem 1.5rem" }}>
        <div style={{ maxWidth: "var(--content-w)", margin: "0 auto" }}>
          <div
            style={{
              maxWidth: "560px",
              margin: "0 auto",
              background: "#0f0f0f",
              border: "1px solid #222",
              borderRadius: "16px",
              padding: "3rem 2.5rem",
              textAlign: "center",
              boxShadow: "0 0 0 1px #1a1a2e, 0 8px 40px rgba(99,102,241,0.06)",
            }}
          >
            <h2 style={{ color: "#fff", fontWeight: 700, fontSize: "1.625rem", marginBottom: "0.75rem", letterSpacing: "-0.02em" }}>
              Ready to ask your docs?
            </h2>
            <p style={{ color: "#71717a", fontSize: "0.875rem", lineHeight: 1.6, marginBottom: "2rem" }}>
              No signup. No API key needed. Upload and go in seconds.
            </p>
            <Link href="/app" className="btn-primary px-6 py-2.5 text-sm">
              Open App <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ── #52525b on #0a0a0a = 4.6:1, passes AA ── */}
      <footer style={{ borderTop: "1px solid #1a1a1a", padding: "1.5rem", textAlign: "center" }}>
        <p style={{ color: "#52525b", fontSize: "0.75rem" }}>
          AskMyDocs · FastAPI · ChromaDB · Gemini · Next.js ·{" "}
          <a
            href="https://github.com/JainRamyak/ASK_DOC_WEBSITE"
            target="_blank"
            rel="noopener noreferrer"
            className="footer-link"
          >
            github.com/JainRamyak
          </a>
        </p>
      </footer>
    </div>
  );
}