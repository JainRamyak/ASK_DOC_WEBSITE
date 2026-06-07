const API_URL = process.env.NEXT_PUBLIC_API_URL;

function getApiBase(): string {
  if (!API_URL) {
    throw new Error(
      "NEXT_PUBLIC_API_URL is not set. Add it to .env.local (e.g. http://localhost:8000)"
    );
  }
  return API_URL.replace(/\/$/, ""); // strip trailing slash
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

export async function uploadDocument(file: File): Promise<{
  session_id: string;
  filename: string;
  chunks: number;
}> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${getApiBase()}/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Upload failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function askQuestion(
  question: string,
  sessionId: string
): Promise<{
  answer: string;
  sources: Array<{ source: string; score: number }>;
}> {
  const res = await fetch(`${getApiBase()}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Query failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  try {
    await fetch(`${getApiBase()}/sessions/${sessionId}`, {
      method: "DELETE",
    });
  } catch {
    // Best-effort delete — don't block UI reset on network failure
  }
}