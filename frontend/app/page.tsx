import Link from "next/link";
import { ArrowRight, FileText, Github, ShieldCheck, Sparkles } from "lucide-react";

const STEPS = [
  {
    mark: "upload",
    title: "Upload your notes",
    description:
      "PDF, Word, or Markdown, any number of pages or files. Everything is split into overlapping passages and embedded locally — nothing leaves the server just to be indexed.",
  },
  {
    mark: "retrieve",
    title: "Find the right passage",
    description:
      "Your question is matched against every passage, then a cross-encoder reads the question and each candidate together to rank what's actually relevant — not just what merely looks similar.",
  },
  {
    mark: "answer or refuse",
    title: "Answer, or say so honestly",
    description:
      "If the best match is still too weak, the system refuses before ever calling the language model. It won't fill the gap with outside knowledge — that check happens in code, not in a prompt asking politely.",
  },
];

const STACK = [
  { name: "FastAPI", desc: "REST backend" },
  { name: "ChromaDB", desc: "Persistent per-session vector store" },
  { name: "sentence-transformers", desc: "Local embeddings, no API key needed" },
  { name: "Cross-encoder rerank", desc: "Relevance scoring before any answer" },
  { name: "Next.js", desc: "Upload + chat frontend" },
];

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-[var(--color-ink)] text-[var(--color-ink-text)]">
      <header className="flex items-center justify-between px-6 py-5 md:px-12">
        <span className="font-display text-lg tracking-tight">AskMyDocs</span>
        <a
          href="https://github.com/JainRamyak/ASK_DOC_WEBSITE"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 text-sm text-[var(--color-ink-muted)] hover:text-[var(--color-ink-text)] transition-colors"
        >
          <Github size={16} /> Source
        </a>
      </header>

      {/* Hero */}
      <section className="px-6 pt-10 pb-20 md:px-12 md:pt-16">
        <div className="mx-auto max-w-3xl">
          <p className="mb-4 flex items-center gap-2 text-sm uppercase tracking-widest text-[var(--color-ink-muted)]">
            <Sparkles size={14} /> Open source · self-hostable · free to run
          </p>
          <h1 className="font-display text-4xl leading-[1.1] md:text-6xl">
            Ask your notes a question.
            <br />
            Get an answer with{" "}
            <span className="citation-mark">the receipt.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg text-[var(--color-ink-muted)]">
            Upload class notes, a contract, a research paper — anything with
            pages. AskMyDocs answers strictly from what you gave it, and
            tells you plainly when the answer isn&apos;t in there.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link
              href="/app"
              className="flex items-center gap-2 rounded-full bg-[var(--color-highlight)] px-6 py-3 font-medium text-[#1a1a1a] transition-transform hover:scale-[1.03]"
            >
              Try it <ArrowRight size={16} />
            </Link>
            <a
              href="#how-it-works"
              className="flex items-center gap-2 rounded-full border border-white/15 px-6 py-3 text-[var(--color-ink-text)] transition-colors hover:border-white/40"
            >
              How it works
            </a>
          </div>
        </div>
      </section>

      {/* Example answer card — the "paper" surface */}
      <section className="px-6 pb-20 md:px-12">
        <div className="mx-auto max-w-2xl rounded-2xl bg-[var(--color-paper)] p-6 text-[#1a1a1a] shadow-2xl md:p-8">
          <p className="mb-3 flex items-center gap-2 text-xs uppercase tracking-wide text-[#6b6252]">
            <FileText size={14} /> class-notes-week4.pdf
          </p>
          <p className="font-display text-lg leading-relaxed">
            Photosynthesis converts light energy into chemical energy stored
            in glucose, using carbon dioxide and water as inputs{" "}
            <span className="citation-mark">[1]</span>. The reaction occurs
            primarily in the chloroplast <span className="citation-mark">[2]</span>.
          </p>
          <p className="mt-4 border-t border-[var(--color-paper-line)] pt-3 text-sm text-[#6b6252]">
            Sources: [1] p.4 &middot; [2] p.5
          </p>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-6 py-20 md:px-12">
        <div className="mx-auto max-w-4xl">
          <h2 className="font-display text-2xl md:text-3xl">How it works</h2>
          <div className="mt-10 grid gap-8 md:grid-cols-3">
            {STEPS.map((step) => (
              <div key={step.title}>
                <p className="font-mono-tight text-xs uppercase tracking-widest text-[var(--color-highlight)]">
                  {step.mark}
                </p>
                <h3 className="mt-2 font-display text-xl">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[var(--color-ink-muted)]">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Stack */}
      <section className="border-t border-white/10 px-6 py-16 md:px-12">
        <div className="mx-auto max-w-4xl">
          <p className="mb-6 flex items-center gap-2 text-sm text-[var(--color-ink-muted)]">
            <ShieldCheck size={16} /> Built with, and only with, what it needs
          </p>
          <div className="flex flex-wrap gap-x-8 gap-y-3">
            {STACK.map((item) => (
              <div key={item.name} className="text-sm">
                <span className="font-medium text-[var(--color-ink-text)]">
                  {item.name}
                </span>
                <span className="text-[var(--color-ink-muted)]"> — {item.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="px-6 py-10 text-center text-xs text-[var(--color-ink-muted)] md:px-12">
        MIT licensed. Fork it, self-host it, break it, send a PR.
      </footer>
    </main>
  );
}
