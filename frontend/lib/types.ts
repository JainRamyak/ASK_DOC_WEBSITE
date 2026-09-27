export interface SkippedFile {
  filename: string;
  reason: "unreadable" | "no_text";
  message: string;
}

export interface AlreadyIndexedFile {
  filename: string;
  hash: string;
}

export interface UploadResponse {
  session_id: string;
  /** Only files that contributed text to the index. */
  filenames: string[];
  /** Files that were uploaded but yielded no text. Sent by /upload, not /upload-url. */
  skipped?: SkippedFile[];
  /** Files/URLs whose content was already indexed in this session, so
   *  they weren't re-indexed. Sent by both /upload and /upload-url. */
  already_indexed?: AlreadyIndexedFile[];
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
