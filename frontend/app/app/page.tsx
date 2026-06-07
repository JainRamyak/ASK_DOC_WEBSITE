"use client";
import { useState, useRef, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import ReactMarkdown from "react-markdown";
import Link from "next/link";
import {
  Upload,
  Send,
  FileText,
  RotateCcw,
  Loader2,
  CheckCircle2,
  ArrowLeft,
  Sparkles,
  BookOpen,
} from "lucide-react";
import { uploadDocument, askQuestion, deleteSession } from "@/lib/api";

/* lucide-react@1.x dropped Github export */
function GithubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Array<{ source: string; score: number }>;
}

/* Truncate long filenames preserving extension */
function shortName(name: string | null, max = 40): string {
  if (!name) return "";
  if (name.length <= max) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  return name.slice(0, max - ext.length - 1) + "…" + ext;
}

export default function AppPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [chunkCount, setChunkCount] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, asking]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    maxFiles: 1,
    maxSize: 20 * 1024 * 1024,
    onDrop: async (accepted, rejected) => {
      setUploadError(null);
      if (rejected.length > 0) {
        setUploadError("File rejected — must be PDF, TXT, MD, or DOCX under 20 MB.");
        return;
      }
      if (!accepted[0]) return;
      setUploading(true);
      try {
        const res = await uploadDocument(accepted[0]);
        setSessionId(res.session_id);
        setFilename(res.filename);
        setChunkCount(res.chunks);
        setMessages([
          {
            role: "assistant",
            content: `Ready. I've indexed **${res.chunks} chunks** from **${res.filename}**.\n\nAsk me anything about it.`,
          },
        ]);
      } catch (e: unknown) {
        setUploadError("Upload failed: " + (e instanceof Error ? e.message : String(e)));
      } finally {
        setUploading(false);
      }
    },
  });

  const handleAsk = async () => {
    if (!input.trim() || !sessionId || asking) return;
    const question = input.trim();
    setInput("");
    setQueryError(null);
    setMessages((m) => [...m, { role: "user", content: question }]);
    setAsking(true);
    try {
      const res = await askQuestion(question, sessionId);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
    } catch (e: unknown) {
      setQueryError("Query failed: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setAsking(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const handleReset = async () => {
    if (sessionId) await deleteSession(sessionId);
    setSessionId(null);
    setFilename(null);
    setChunkCount(0);
    setMessages([]);
    setInput("");
    setUploadError(null);
    setQueryError(null);
  };

  return (
    <div style={{ height: "100dvh", display: "flex", flexDirection: "column", background: "#0a0a0a" }}>

      {/* ── Header ────────────────────────────────────────── */}
      <header style={{ borderBottom: "1px solid #1a1a1a", background: "#0a0a0a", flexShrink: 0 }}>
        <div
          style={{ maxWidth: "var(--content-w)", margin: "0 auto", padding: "0 1.5rem", height: "52px", display: "flex", alignItems: "center", justifyContent: "space-between" }}
        >
          {/* Left: breadcrumb */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
            <Link
              href="/"
              style={{ display: "flex", alignItems: "center", gap: "4px", color: "#52525b", fontSize: "0.8125rem", transition: "color 0.15s", flexShrink: 0 }}
              onMouseEnter={e => (e.currentTarget.style.color = "#a1a1aa")}
              onMouseLeave={e => (e.currentTarget.style.color = "#52525b")}
            >
              <ArrowLeft size={13} />
              <span className="hidden sm:inline">Home</span>
            </Link>

            <span style={{ color: "#2a2a2a", fontSize: "0.875rem" }}>/</span>
            <span style={{ color: "#a1a1aa", fontWeight: 500, fontSize: "0.875rem", flexShrink: 0 }}>AskMyDocs</span>

            {filename && (
              <>
                <span style={{ color: "#2a2a2a", fontSize: "0.875rem" }}>/</span>
                <span
                  style={{ color: "#818cf8", fontSize: "0.8125rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "180px" }}
                  title={filename}
                >
                  {shortName(filename, 30)}
                </span>
              </>
            )}
          </div>

          {/* Right: actions */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
            {sessionId && (
              <button
                onClick={handleReset}
                style={{
                  display: "flex", alignItems: "center", gap: "5px",
                  color: "#71717a", fontSize: "0.75rem", padding: "5px 10px",
                  border: "1px solid #222", borderRadius: "6px", background: "transparent",
                  cursor: "pointer", transition: "color 0.15s, border-color 0.15s",
                }}
                onMouseEnter={e => { e.currentTarget.style.color = "#a1a1aa"; e.currentTarget.style.borderColor = "#3f3f3f"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "#71717a"; e.currentTarget.style.borderColor = "#222"; }}
              >
                <RotateCcw size={11} />
                New doc
              </button>
            )}
            <a
              href="https://github.com/JainRamyak/ASK_DOC_WEBSITE"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "#52525b", transition: "color 0.15s", display: "flex" }}
              aria-label="View on GitHub"
              onMouseEnter={e => (e.currentTarget.style.color = "#71717a")}
              onMouseLeave={e => (e.currentTarget.style.color = "#52525b")}
            >
              <GithubIcon size={16} />
            </a>
          </div>
        </div>
      </header>

      {/* ── Body ──────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {!sessionId ? (

          /* ── Upload panel ─────────────────────────────── */
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "2rem" }}>
            <div className="scale-in" style={{ width: "100%", maxWidth: "420px" }}>

              {/* Icon */}
              <div style={{ display: "flex", justifyContent: "center", marginBottom: "1.5rem" }}>
                <div style={{ width: "52px", height: "52px", borderRadius: "14px", display: "flex", alignItems: "center", justifyContent: "center", background: "#0d0d1f", border: "1px solid #1e1e38" }}>
                  <BookOpen size={22} style={{ color: "#818cf8" }} />
                </div>
              </div>

              <h2 style={{ color: "#e4e4e7", fontWeight: 600, fontSize: "1.125rem", textAlign: "center", marginBottom: "0.375rem" }}>
                Upload a document
              </h2>
              <p style={{ color: "#71717a", fontSize: "0.8125rem", textAlign: "center", marginBottom: "1.5rem" }}>
                PDF · TXT · MD · DOCX — max 20 MB
              </p>

              {/* Dropzone */}
              <div
                {...getRootProps()}
                className={`drop-zone${isDragActive ? " drop-active" : ""}`}
                style={{ padding: "2.5rem 1.5rem", textAlign: "center" }}
              >
                <input {...getInputProps()} />
                {uploading ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
                    <Loader2 size={24} className="animate-spin" style={{ color: "#6366f1" }} />
                    <p style={{ color: "#a1a1aa", fontSize: "0.875rem" }}>Chunking &amp; embedding…</p>
                    <p style={{ color: "#52525b", fontSize: "0.75rem" }}>This may take a few seconds</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
                    <Upload size={22} style={{ color: isDragActive ? "#818cf8" : "#52525b" }} />
                    <p style={{ color: "#a1a1aa", fontSize: "0.875rem" }}>
                      {isDragActive ? "Release to upload" : "Drag & drop or click to browse"}
                    </p>
                    <button className="btn-primary" style={{ padding: "6px 14px", fontSize: "0.8125rem", marginTop: "4px" }}>
                      Choose file
                    </button>
                  </div>
                )}
              </div>

              {/* Error */}
              {uploadError && (
                <div style={{ marginTop: "10px", padding: "8px 12px", borderRadius: "8px", background: "#1c0a0a", border: "1px solid #3f1010", color: "#f87171", fontSize: "0.8125rem", textAlign: "center" }}>
                  {uploadError}
                </div>
              )}
            </div>
          </div>

        ) : (

          /* ── Chat panel ───────────────────────────────── */
          <div
            style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", maxWidth: "var(--content-w)", margin: "0 auto", width: "100%", padding: "0 1.5rem" }}
          >
            {/* File status bar — compact single row */}
            <div
              style={{ display: "flex", alignItems: "center", gap: "8px", padding: "6px 10px", margin: "10px 0 6px", borderRadius: "8px", background: "#0f0f0f", border: "1px solid #1a1a1a", flexShrink: 0 }}
            >
              <FileText size={12} style={{ color: "#6366f1", flexShrink: 0 }} />
              <span style={{ color: "#a1a1aa", fontSize: "0.8125rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }} title={filename ?? ""}>
                {shortName(filename ?? "", 50)}
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "0.6875rem", padding: "2px 8px", borderRadius: "100px", background: "#052e16", color: "#4ade80", flexShrink: 0, whiteSpace: "nowrap" }}>
                <CheckCircle2 size={9} />
                {chunkCount} chunks indexed
              </span>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "16px", paddingBottom: "8px" }}>
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className="fade-in"
                  style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", alignItems: "flex-start" }}
                >
                  {/* AI avatar */}
                  {msg.role === "assistant" && (
                    <div style={{ width: "26px", height: "26px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", marginRight: "8px", marginTop: "1px", flexShrink: 0, background: "#0d0d1f", border: "1px solid #1e1e38" }}>
                      <Sparkles size={12} style={{ color: "#818cf8" }} />
                    </div>
                  )}

                  <div
                    style={{
                      /* FIX A1: cap at 600px for readability instead of 80% of container */
                      maxWidth: "min(600px, 82%)",
                      borderRadius: msg.role === "user"
                        ? "12px 4px 12px 12px"   /* FIX A7: asymmetric — no top-right corner */
                        : "4px 12px 12px 12px",  /* FIX A7: asymmetric — no top-left corner */
                      padding: "10px 14px",
                      background: msg.role === "user" ? "#4f46e5" : "#0f0f0f",
                      border: msg.role === "assistant" ? "1px solid #1a1a1a" : "none",
                    }}
                  >
                    {/* FIX A4: replaced dead 'prose' with .md-body */}
                    <div className="md-body" style={{ fontSize: "0.875rem" }}>
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>

                    {/* Source citations */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div style={{ marginTop: "10px", paddingTop: "10px", borderTop: "1px solid #1a1a1a" }}>
                        {/* FIX A5: sources label visible */}
                        <p style={{ color: "#52525b", fontSize: "0.6875rem", fontWeight: 500, marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                          Sources
                        </p>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
                          {msg.sources.map((s, j) => (
                            <span key={j} className="citation-pill" title={s.source}>
                              <span style={{ fontWeight: 600, opacity: 0.7 }}>[{j + 1}]</span>
                              <span style={{ maxWidth: "130px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {s.source}
                              </span>
                              {s.score > 0 && (
                                <span style={{ opacity: 0.45, fontFamily: "ui-monospace, monospace", fontSize: "10px" }}>
                                  {(s.score * 100).toFixed(0)}%
                                </span>
                              )}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {asking && (
                <div className="fade-in" style={{ display: "flex", alignItems: "flex-start" }}>
                  <div style={{ width: "26px", height: "26px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", marginRight: "8px", marginTop: "1px", flexShrink: 0, background: "#0d0d1f", border: "1px solid #1e1e38" }}>
                    <Sparkles size={12} style={{ color: "#818cf8" }} />
                  </div>
                  <div style={{ padding: "12px 14px", borderRadius: "4px 12px 12px 12px", background: "#0f0f0f", border: "1px solid #1a1a1a" }}>
                    <div style={{ display: "flex", gap: "4px", alignItems: "center", height: "14px" }}>
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          style={{
                            width: "5px", height: "5px", borderRadius: "50%", background: "#4f46e5",
                            animation: `bounce-dot 1.2s ease-in-out ${i * 0.18}s infinite`,
                            display: "inline-block",
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Query error */}
              {queryError && (
                <div style={{ background: "#1c0a0a", border: "1px solid #3f1010", borderRadius: "8px", padding: "8px 12px", color: "#f87171", fontSize: "0.8125rem", textAlign: "center", maxWidth: "480px", margin: "0 auto" }}>
                  {queryError}
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input bar — FIX A3: focus-within glow via .input-bar class */}
            <div className="input-bar" style={{ display: "flex", gap: "6px", padding: "6px", marginBottom: "16px", flexShrink: 0 }}>
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAsk()}
                placeholder="Ask anything about your document…"
                style={{ flex: 1, background: "transparent", padding: "6px 8px", fontSize: "0.875rem", color: "#e4e4e7", outline: "none", border: "none" }}
                autoFocus
                disabled={asking}
              />
              {/* FIX A8: disabled opacity 30 instead of 20 */}
              <button
                onClick={handleAsk}
                disabled={!input.trim() || asking}
                style={{
                  padding: "7px 12px", borderRadius: "6px", background: "#4f46e5", border: "none", cursor: "pointer",
                  transition: "opacity 0.15s", opacity: (!input.trim() || asking) ? 0.3 : 1,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
                aria-label="Send message"
              >
                {asking
                  ? <Loader2 size={14} className="animate-spin" style={{ color: "#fff" }} />
                  : <Send size={14} style={{ color: "#fff" }} />
                }
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}