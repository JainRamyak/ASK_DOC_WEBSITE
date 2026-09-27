"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import ReactMarkdown from "react-markdown";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  FileText,
  Info,
  Link2,
  Loader2,
  RotateCcw,
  Send,
  ShieldAlert,
  TriangleAlert,
  Upload,
} from "lucide-react";

import { askQuestion, deleteSession, humanizeError, uploadDocuments, uploadUrl } from "@/lib/api";
import { AlreadyIndexedFile, ChatMessage, SkippedFile } from "@/lib/types";

function shortName(name: string, max = 34): string {
  if (name.length <= max) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  return name.slice(0, max - ext.length - 1) + "…" + ext;
}

export default function AppPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filenames, setFilenames] = useState<string[]>([]);
  const [skipped, setSkipped] = useState<SkippedFile[]>([]);
  const [alreadyIndexed, setAlreadyIndexed] = useState<AlreadyIndexedFile[]>([]);
  const [chunkCount, setChunkCount] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [showUrlInput, setShowUrlInput] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, asking]);

  const handleUpload = useCallback(
    async (files: File[], appendToExisting: boolean) => {
      setError(null);
      setUploading(true);
      try {
        const res = await uploadDocuments(files, appendToExisting ? sessionId ?? undefined : undefined);
        setSessionId(res.session_id);
        setFilenames((prev) => (appendToExisting ? [...prev, ...res.filenames] : res.filenames));
        setSkipped((prev) => (appendToExisting ? [...prev, ...(res.skipped ?? [])] : res.skipped ?? []));
        setAlreadyIndexed((prev) =>
          appendToExisting ? [...prev, ...(res.already_indexed ?? [])] : res.already_indexed ?? []
        );
        setChunkCount((prev) => (appendToExisting ? prev + res.chunks : res.chunks));
      } catch (e) {
        setError(humanizeError(e));
      } finally {
        setUploading(false);
      }
    },
    [sessionId]
  );

  const handleUrlSubmit = useCallback(
    async (appendToExisting: boolean) => {
      const url = urlInput.trim();
      if (!url || uploading) return;
      setError(null);
      setUploading(true);
      try {
        const res = await uploadUrl(url, appendToExisting ? sessionId ?? undefined : undefined);
        setSessionId(res.session_id);
        setFilenames((prev) => (appendToExisting ? [...prev, ...res.filenames] : res.filenames));
        setSkipped((prev) => (appendToExisting ? [...prev, ...(res.skipped ?? [])] : res.skipped ?? []));
        setAlreadyIndexed((prev) =>
          appendToExisting ? [...prev, ...(res.already_indexed ?? [])] : res.already_indexed ?? []
        );
        setChunkCount((prev) => (appendToExisting ? prev + res.chunks : res.chunks));
        setUrlInput("");
        setShowUrlInput(false);
      } catch (e) {
        setError(humanizeError(e));
      } finally {
        setUploading(false);
      }
    },
    [urlInput, sessionId, uploading]
  );

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length === 0 || uploading) return;
      handleUpload(accepted, Boolean(sessionId));
    },
    [handleUpload, sessionId, uploading]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
    accept: {
      "application/pdf": [".pdf"],
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
  });

  async function handleAsk() {
    if (!question.trim() || !sessionId || asking) return;
    const q = question.trim();
    // Prior user questions in this session, most recent last. Only
    // acted on by the backend if ENABLE_QUERY_REWRITING=true — sending
    // it unconditionally is harmless (and simpler) when the feature is off.
    const priorQuestions = messages.filter((m) => m.role === "user").map((m) => m.content);
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setAsking(true);
    setError(null);
    try {
      const res = await askQuestion(q, sessionId, priorQuestions);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          grounded: res.grounded,
          reason: res.reason,
        },
      ]);
    } catch (e) {
      setError(humanizeError(e));
    } finally {
      setAsking(false);
    }
  }

  async function handleReset() {
    if (sessionId) await deleteSession(sessionId);
    setSessionId(null);
    setFilenames([]);
    setSkipped([]);
    setAlreadyIndexed([]);
    setChunkCount(0);
    setMessages([]);
    setError(null);
  }

  return (
    <main className="flex min-h-screen flex-col bg-[var(--color-ink)] text-[var(--color-ink-text)]">
      <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <Link href="/" className="flex items-center gap-2 text-sm text-[var(--color-ink-muted)] hover:text-[var(--color-ink-text)]">
          <ArrowLeft size={16} /> AskMyDocs
        </Link>
        {sessionId && (
          <button
            onClick={handleReset}
            className="flex items-center gap-2 text-sm text-[var(--color-ink-muted)] hover:text-[var(--color-ink-text)]"
          >
            <RotateCcw size={14} /> New session
          </button>
        )}
      </header>

      {!sessionId ? (
        <div className="flex flex-1 items-center justify-center px-6">
          <div className="w-full max-w-lg">
            <div
              {...getRootProps()}
              className={`cursor-pointer rounded-2xl border-2 border-dashed p-14 text-center transition-colors ${
                isDragActive
                  ? "border-[var(--color-highlight)] bg-[var(--color-highlight)]/5"
                  : "border-white/20 hover:border-white/40"
              }`}
            >
              <input {...getInputProps()} />
              {uploading ? (
                <Loader2 size={28} className="mx-auto animate-spin text-[var(--color-highlight)]" />
              ) : (
                <Upload size={28} className="mx-auto text-[var(--color-ink-muted)]" />
              )}
              <p className="mt-4 font-display text-lg">
                {uploading ? "Reading your document…" : "Drop files here, or click to browse"}
              </p>
              <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
                PDF, DOCX, TXT, or MD &middot; up to 10 files at once
              </p>
            </div>

            <div className="my-4 flex items-center gap-3 text-xs uppercase tracking-widest text-[var(--color-ink-muted)]">
              <div className="h-px flex-1 bg-white/10" />
              or paste a URL
              <div className="h-px flex-1 bg-white/10" />
            </div>

            <div className="flex items-center gap-2 rounded-full border border-white/15 bg-[var(--color-ink-raised)] px-4 py-2">
              <Link2 size={16} className="shrink-0 text-[var(--color-ink-muted)]" />
              <input
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit(false)}
                placeholder="https://example.com/article"
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--color-ink-muted)]"
              />
              <button
                onClick={() => handleUrlSubmit(false)}
                disabled={uploading || !urlInput.trim()}
                className="rounded-full bg-[var(--color-highlight)] px-3 py-1 text-xs font-medium text-[#1a1a1a] disabled:opacity-40"
              >
                Fetch
              </button>
            </div>

            {error && <p className="mt-4 text-center text-sm text-red-400">{error}</p>}
          </div>
        </div>
      ) : (
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-6 py-6">
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-[var(--color-ink-raised)] px-4 py-3 text-sm">
            <CheckCircle2 size={16} className="shrink-0 text-[var(--color-highlight)]" />
            <span>
              {filenames.map((f) => shortName(f)).join(", ")} &middot; {chunkCount} passages indexed
            </span>
            <div className="ml-auto flex items-center gap-3">
              <button
                onClick={() => setShowUrlInput((v) => !v)}
                className="text-[var(--color-ink-muted)] underline decoration-dotted hover:text-[var(--color-ink-text)]"
              >
                add URL
              </button>
              <label
                {...getRootProps()}
                className="cursor-pointer text-[var(--color-ink-muted)] underline decoration-dotted hover:text-[var(--color-ink-text)]"
              >
                <input {...getInputProps()} />
                add more files
              </label>
            </div>
          </div>

          {skipped.length > 0 && (
            <div
              role="status"
              className="mb-4 rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200"
            >
              <div className="flex items-center gap-2 font-medium">
                <TriangleAlert size={16} className="shrink-0" />
                {skipped.length === 1 ? "1 file wasn't indexed" : `${skipped.length} files weren't indexed`}
              </div>
              <ul className="mt-1 space-y-0.5 pl-6 text-amber-100/80">
                {skipped.map((s, i) => (
                  <li key={`${s.filename}-${i}`}>
                    <span className="font-medium">{shortName(s.filename)}</span> &mdash; {s.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {alreadyIndexed.length > 0 && (
            <div
              role="status"
              className="mb-4 rounded-xl border border-white/10 bg-[var(--color-ink-raised)] px-4 py-3 text-sm text-[var(--color-ink-muted)]"
            >
              <div className="flex items-center gap-2 font-medium text-[var(--color-ink-text)]">
                <Info size={16} className="shrink-0" />
                {alreadyIndexed.length === 1
                  ? "1 file was already indexed"
                  : `${alreadyIndexed.length} files were already indexed`}
              </div>
              <ul className="mt-1 space-y-0.5 pl-6">
                {alreadyIndexed.map((a, i) => (
                  <li key={`${a.filename}-${i}`}>
                    <span className="font-medium text-[var(--color-ink-text)]">{shortName(a.filename)}</span> is
                    identical to a document already in this session &mdash; not indexed again.
                  </li>
                ))}
              </ul>
            </div>
          )}

          {showUrlInput && (
            <div className="mb-4 flex items-center gap-2 rounded-full border border-white/15 bg-[var(--color-ink-raised)] px-4 py-2">
              <Link2 size={16} className="shrink-0 text-[var(--color-ink-muted)]" />
              <input
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit(true)}
                placeholder="https://example.com/article"
                autoFocus
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--color-ink-muted)]"
              />
              <button
                onClick={() => handleUrlSubmit(true)}
                disabled={uploading || !urlInput.trim()}
                className="rounded-full bg-[var(--color-highlight)] px-3 py-1 text-xs font-medium text-[#1a1a1a] disabled:opacity-40"
              >
                {uploading ? <Loader2 size={12} className="animate-spin" /> : "Fetch"}
              </button>
            </div>
          )}

          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto">
            {messages.length === 0 && (
              <p className="mt-10 text-center text-sm text-[var(--color-ink-muted)]">
                Ask anything about what you uploaded.
              </p>
            )}
            {messages.map((m, i) => (
              <MessageBubble key={i} message={m} />
            ))}
            {asking && (
              <div className="flex items-center gap-2 text-sm text-[var(--color-ink-muted)]">
                <Loader2 size={14} className="animate-spin" /> Searching your documents…
              </div>
            )}
          </div>

          {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

          <div className="mt-4 flex items-center gap-2 rounded-full border border-white/15 bg-[var(--color-ink-raised)] px-4 py-2">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAsk()}
              placeholder="Ask a question about your document…"
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--color-ink-muted)]"
            />
            <button
              onClick={handleAsk}
              disabled={asking || !question.trim()}
              className="rounded-full bg-[var(--color-highlight)] p-2 text-[#1a1a1a] disabled:opacity-40"
              aria-label="Send question"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-[var(--color-ink-raised)] px-4 py-2.5 text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const notGrounded = message.grounded === false;

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[85%] rounded-2xl rounded-bl-sm px-5 py-4 ${
          notGrounded
            ? "border border-white/15 bg-[var(--color-ink-raised)] text-[var(--color-ink-muted)]"
            : "bg-[var(--color-paper)] text-[#1a1a1a]"
        }`}
      >
        {notGrounded && (
          <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide">
            <ShieldAlert size={13} />
            {message.reason === "no_session"
              ? "Session unavailable — please re-upload"
              : "Not in the document"}
          </p>
        )}
        <div className="markdown-body font-display text-[15px] leading-relaxed">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
        {message.sources && message.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--color-paper-line)] pt-3">
            {message.sources.map((s, i) => (
              <span
                key={i}
                className="citation-mark flex items-center gap-1 rounded-full text-xs"
                title={`relevance score: ${s.score.toFixed(2)}`}
              >
                <FileText size={11} /> {s.source}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
