import { ApiError, AskResponse, UploadResponse } from "./types";

/**
 * Normalizes any error thrown by the fetch calls below into a message
 * that's actually meaningful to the person looking at it. Without this,
 * a client-side AbortSignal timeout ("signal timed out") and a dead
 * network ("Failed to fetch") surfaced as raw DOM/JS error text
 * indistinguishable from a real backend failure — none of which a user
 * can act on. ApiError carries the backend's own detail message and is
 * passed through unchanged, since that one *is* meaningful as-is.
 */
export function humanizeError(e: unknown): string {
  if (e instanceof ApiError) {
    return e.message;
  }
  if (e instanceof DOMException && e.name === "TimeoutError") {
    return "The request timed out. The backend may be busy — please try again.";
  }
  if (e instanceof TypeError) {
    return "Could not reach the server. Is the backend running?";
  }
  return e instanceof Error ? e.message : "Something went wrong.";
}

function getApiBase(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    throw new Error(
      "NEXT_PUBLIC_API_URL is not set. Add it to .env.local (e.g. http://localhost:8000)."
    );
  }
  return url.replace(/\/$/, "");
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? `Request failed (HTTP ${res.status})`;
  } catch {
    return `Request failed (HTTP ${res.status})`;
  }
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/health`, {
      signal: AbortSignal.timeout(4000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Upload one or more files. Pass `sessionId` to add files to an
 * existing session instead of starting a new one.
 */
export async function uploadDocuments(
  files: File[],
  sessionId?: string
): Promise<UploadResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  if (sessionId) {
    form.append("session_id", sessionId);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000); // 2 min

  try {
    const res = await fetch(`${getApiBase()}/upload`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new ApiError(await parseErrorDetail(res), res.status);
    }
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Ingest a single live URL. Pass `sessionId` to add it to an existing
 * session instead of starting a new one.
 */
export async function uploadUrl(
  url: string,
  sessionId?: string
): Promise<UploadResponse> {
  const res = await fetch(`${getApiBase()}/upload-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, session_id: sessionId }),
    signal: AbortSignal.timeout(30_000), // the backend's own fetch is capped at 10s
  });
  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }
  return res.json();
}

export async function askQuestion(
  question: string,
  sessionId: string,
  history?: string[]
): Promise<AskResponse> {
  const res = await fetch(`${getApiBase()}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId, history }),
    signal: AbortSignal.timeout(60_000), // LLM generation can be slow
  });
  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  try {
    await fetch(`${getApiBase()}/sessions/${sessionId}`, { method: "DELETE" });
  } catch {
    // best-effort — don't block the UI reset on a network failure
  }
}
