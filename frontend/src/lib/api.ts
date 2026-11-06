import type { Msg, ThreadSummary, turnsFromThread } from "./agent";
import type {
  Chat,
  ChatMemory,
  ChatStats,
  Health,
  Job,
  Participant,
  Persona,
  Project,
  ProjectDetail,
  ReplyGraph,
} from "./types";

// Set NEXT_PUBLIC_API_URL at build time for deployment (the Render URL). Inlined into the bundle.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
  /** True when the server could not be reached at all. */
  get offline() {
    return this.status === 0;
  }
}

/** FastAPI errors look like {"detail": "..."} or {"detail": [{"msg": ...}]}. */
function reason(body: string): string {
  try {
    const d = JSON.parse(body).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  } catch {
    /* not JSON */
  }
  return body.slice(0, 200);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(API_URL + path, init);
  } catch {
    throw new ApiError(0, `Can't reach ${API_URL}`);
  }
  if (!r.ok) throw new ApiError(r.status, reason(await r.text()));
  return r.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/health"),
  projects: () => request<Project[]>("/projects"),
  createProject: (name: string) => request<Project>("/projects", json("POST", { name })),
  project: (pid: number) => request<ProjectDetail>(`/projects/${pid}`),
  renameProject: (pid: number, name: string) => request<Project>(`/projects/${pid}`, json("PATCH", { name })),
  chatStats: (pid: number, cid: number) => request<ChatStats>(`/projects/${pid}/chats/${cid}/stats`),
  message: (pid: number, mid: number, context = 5) =>
    request<{ message: Msg; before: Msg[]; after: Msg[] }>(`/projects/${pid}/messages/${mid}?context=${context}`),
  mediaUrl: (pid: number, mediaId: number) => `${API_URL}/projects/${pid}/media/${mediaId}`,
  memory: (pid: number, cid: number) => request<ChatMemory>(`/projects/${pid}/chats/${cid}/memory`),
  /** A roast as WAV from Gemini's voice. Throws when the server can't, so the caller can use the browser's voice. */
  speak: async (pid: number, text: string): Promise<Blob> => {
    const r = await fetch(`${API_URL}/projects/${pid}/tts`, json("POST", { text }));
    if (!r.ok) throw new ApiError(r.status, "text to speech failed");
    return r.blob();
  },
  graph: (pid: number, cid: number) => request<ReplyGraph>(`/projects/${pid}/chats/${cid}/graph`),
  persona: (pid: number, partId: number, cid?: number) =>
    request<Persona>(`/projects/${pid}/participants/${partId}/persona${cid ? `?chat_id=${cid}` : ""}`),
  threads: (pid: number) => request<ThreadSummary[]>(`/projects/${pid}/threads`),
  thread: (pid: number, tid: number) =>
    request<ThreadSummary & { messages: Parameters<typeof turnsFromThread>[1] }>(`/projects/${pid}/threads/${tid}`),
  deleteThread: (pid: number, tid: number) => request<{ deleted: number }>(`/projects/${pid}/threads/${tid}`, { method: "DELETE" }),
  deleteProject: (pid: number) => request<{ deleted: number }>(`/projects/${pid}`, { method: "DELETE" }),
  deleteChat: (pid: number, cid: number) =>
    request<{ deleted: number }>(`/projects/${pid}/chats/${cid}`, { method: "DELETE" }),
  jobs: (pid: number) => request<Job[]>(`/projects/${pid}/jobs`),
  participants: (pid: number) => request<Participant[]>(`/projects/${pid}/participants`),
  updateParticipant: (pid: number, id: number, patch: { is_me?: boolean; roast_opt_out?: boolean }) =>
    request<Participant>(`/projects/${pid}/participants/${id}`, json("PATCH", patch)),
  chats: (pid: number) => request<Chat[]>(`/projects/${pid}/chats`),
};

/** Upload an export with byte progress (fetch cannot report upload progress, XHR can). Resolves with the job id. */
export function uploadChat(
  pid: number,
  file: File,
  onProgress: (fraction: number) => void,
): { promise: Promise<number>; cancel: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<number>((resolve, reject) => {
    xhr.open("POST", `${API_URL}/projects/${pid}/chats`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status === 202) resolve(JSON.parse(xhr.responseText).job_id);
      else reject(new ApiError(xhr.status, reason(xhr.responseText)));
    };
    xhr.onerror = () => reject(new ApiError(0, `Can't reach ${API_URL}`));
    xhr.onabort = () => reject(new ApiError(-1, "Upload cancelled"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
  return { promise, cancel: () => xhr.abort() };
}
