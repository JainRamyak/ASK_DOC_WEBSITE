export interface SkippedFile {
  filename: string;
  reason: "unreadable" | "no_text";
  message: string;
}

export interface UploadResponse {
  session_id: string;
  /** Only files that contributed text to the index. */
  filenames: string[];
  /** Files that were uploaded but yielded no text. Sent by /upload, not /upload-url. */
  skipped?: SkippedFile[];
  chunks: number;
  status: string;
}

export interface Source {
  source: string;
  score: number;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  grounded: boolean;
  reason?: "no_session";
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  grounded?: boolean;
  reason?: "no_session";
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}
