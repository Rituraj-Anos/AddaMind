// Agent runs: the SSE stream from POST /projects/{pid}/agent, folded into a Turn by a pure reducer.
import { API_URL, ApiError } from "./api";

export type AgentKey = "analyzer" | "roaster" | "reply" | "recall";
export type Tone = "wholesome" | "spicy" | "savage";
export type ScopeType = "project" | "chat" | "participant";

export interface Msg {
  id: number;
  chat_id: number;
  ts: string;
  participant_id: number | null;
  sender: string | null;
  kind: string;
  text: string;
  edited: boolean;
  media: { id: number; status: string; result: string | null } | null;
  chat_title?: string | null;
}

export interface Roast {
  text: string;
  status: "ok" | "rewritten";
  evidence_ids: number[];
}
export interface Reply {
  text: string;
  tone: string;
  why: string;
}
export type FinalData = { target: string; tone: Tone; roasts: Roast[]; dropped: number } | { replies: Reply[] } | null;

export type AgentEvent =
  | { type: "thread"; thread_id: number; agent: AgentKey; scope_type: ScopeType; scope_id: number | null }
  | { type: "run_start"; agent: string }
  | { type: "step"; step: number }
  | { type: "llm_attempt"; provider: string; model: string }
  | { type: "llm_error"; provider: string; model: string; kind: string; cooldown_s: number }
  | { type: "llm_skip"; provider: string; model: string; reason: string }
  | { type: "llm_response"; provider: string; model: string; latency_ms: number; tool_calls: number }
  | { type: "text_delta"; text: string }
  | { type: "text_reset" }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; ok: boolean; duration_ms: number; result: unknown }
  | { type: "structuring" }
  | { type: "safety_check"; roasts: number }
  | {
      type: "final";
      text: string;
      citations: Msg[];
      data: FinalData;
      dropped_citations?: number;
      refused?: string;
      steps?: number;
      model?: string;
      duration_ms?: number;
    }
  | { type: "error"; kind: string; message: string };

export interface ToolRow {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "ok" | "failed";
  ms?: number;
  result?: unknown;
}

/** A message seen in tool results, parsed from the "[m:ID] date time · chat · Name: text" lines tools return. */
export interface Seen {
  id: number;
  ts: string;
  chat: string | null;
  sender: string;
  text: string;
}

export interface Turn {
  key: string;
  agent: AgentKey;
  question: string;
  status: "running" | "done" | "error" | "stopped";
  started: number;
  tools: ToolRow[];
  /** What the agent is doing, newest last: the marquee and the screen-reader line. */
  actions: string[];
  model?: string;
  fallbacks: number;
  draft: string;
  checking?: "structuring" | "safety";
  seen: Seen[];
  final?: Extract<AgentEvent, { type: "final" }>;
  error?: string;
  restored?: boolean;
}

export const newTurn = (agent: AgentKey, question: string): Turn => ({
  key: `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
  agent,
  question,
  status: "running",
  started: Date.now(),
  tools: [],
  actions: [],
  fallbacks: 0,
  draft: "",
  seen: [],
});

const LINE = /^\[m:(\d+)\] (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: · (.+?))? · ([^:]+?): ([\s\S]*)$/;

export function parseLine(line: string): Seen | null {
  const m = LINE.exec(line.trim());
  return m ? { id: Number(m[1]), ts: m[2], chat: m[3] ?? null, sender: m[4], text: m[5] } : null;
}

/** Messages a tool result shows: search hits (not their context lines) and messages-around lines. */
export function seenIn(name: string, result: unknown): Seen[] {
  if (!result || typeof result !== "object") return [];
  const r = result as Record<string, unknown>;
  const lines: string[] = [];
  if (name === "search_messages" && Array.isArray(r.results)) {
    for (const x of r.results as { message?: string }[]) if (x.message) lines.push(x.message);
  } else if (name === "get_messages_around" && Array.isArray(r.lines)) {
    lines.push(...(r.lines as string[]));
  } else if (name === "get_media" && typeof r.message === "string") {
    lines.push(r.message);
  }
  return lines.map(parseLine).filter((x): x is Seen => x !== null);
}

const str = (v: unknown) => (typeof v === "string" ? v : "");

/** A short line for the marquee, in plain words. */
export function phrase(name: string, args: Record<string, unknown>): string {
  switch (name) {
    case "search_messages":
      return `Searching "${str(args.query).slice(0, 40)}"`;
    case "get_chat_stats":
      return "Counting every message";
    case "get_reply_graph":
      return "Mapping who replies to whom";
    case "get_mood_series":
      return "Reading the mood month by month";
    case "get_timeline":
      return "Walking the timeline";
    case "get_persona":
      return `Reading ${str(args.participant) || "their"} persona`;
    case "get_media":
      return "Opening a photo or voice note";
    case "get_messages_around":
      return "Reading around a message";
    case "list_chats":
      return "Listing the chats";
    case "list_participants":
      return "Listing the people";
    case "get_inside_jokes":
      return "Looking up the inside jokes";
    default:
      return name.replace(/_/g, " ");
  }
}

const push = (a: string[], s: string) => (a[a.length - 1] === s ? a : [...a, s].slice(-8));

export function applyEvent(t: Turn, ev: AgentEvent): Turn {
  switch (ev.type) {
    case "llm_attempt":
      return { ...t, actions: push(t.actions, t.tools.length ? "Thinking it over" : "Reading the question") };
    case "llm_error":
      return { ...t, fallbacks: t.fallbacks + 1, actions: push(t.actions, "Switching to another model") };
    case "llm_response":
      return { ...t, model: ev.model, draft: ev.tool_calls ? "" : t.draft };
    case "text_delta":
      return { ...t, draft: t.draft + ev.text, actions: push(t.actions, "Writing the answer") };
    case "text_reset":
      return { ...t, draft: "" };
    case "tool_call":
      return {
        ...t,
        tools: [...t.tools, { id: ev.id, name: ev.name, args: ev.args, status: "running" }],
        actions: push(t.actions, phrase(ev.name, ev.args)),
      };
    case "tool_result": {
      const found = seenIn(ev.name, ev.result).filter((s) => !t.seen.some((x) => x.id === s.id));
      return {
        ...t,
        tools: t.tools.map((r) =>
          r.id === ev.id ? { ...r, status: ev.ok ? "ok" : "failed", ms: ev.duration_ms, result: ev.result } : r,
        ),
        seen: [...t.seen, ...found],
      };
    }
    case "structuring":
      return { ...t, checking: "structuring", actions: push(t.actions, "Putting it together") };
    case "safety_check":
      return { ...t, checking: "safety", actions: push(t.actions, "Checking every roast is fair") };
    case "final":
      return { ...t, status: "done", final: ev, draft: "", checking: undefined };
    case "error":
      return {
        ...t,
        status: "error",
        checking: undefined,
        error: ev.kind === "all_models_failed" ? "Every model is busy or out of free quota right now." : ev.message,
        tools: t.tools.map((r) => (r.status === "running" ? { ...r, status: "failed" } : r)),
      };
    default:
      return t;
  }
}

export interface AgentRequest {
  agent: AgentKey;
  message: string;
  scope_type: ScopeType;
  scope_id: number | null;
  thread_id: number | null;
  options: { tone?: Tone; style_of?: string; reply_to?: number };
}

/** POST and yield each Server-Sent Event. EventSource can't POST, so the stream is parsed by hand. */
export async function* streamAgent(pid: number, body: AgentRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
  let r: Response;
  try {
    r = await fetch(`${API_URL}/projects/${pid}/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (signal.aborted) throw e;
    throw new ApiError(0, `Can't reach ${API_URL}`);
  }
  if (!r.ok || !r.body) {
    const text = await r.text();
    let detail = text;
    try {
      detail = JSON.parse(text).detail ?? text;
    } catch {
      /* plain text */
    }
    throw new ApiError(r.status, String(detail).slice(0, 200));
  }
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value.replace(/\r\n/g, "\n");
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      const data = block
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart())
        .join("\n");
      if (data) yield JSON.parse(data) as AgentEvent; // keep-alive comments have no data lines
    }
  }
}

export interface ThreadSummary {
  id: number;
  agent: AgentKey;
  scope_type: ScopeType;
  scope_id: number | null;
  title: string;
  updated_at: string;
}

type Shown =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; tool_calls: { id: string; name: string; args: Record<string, unknown> }[]; data?: FinalData; citations?: Msg[] }
  | { role: "tool"; tool_call_id: string; name: string; text: string };

/** Rebuild turns from a stored thread. Model calls aren't stored; tool calls and the final answer are. */
export function turnsFromThread(agent: AgentKey, messages: Shown[]): Turn[] {
  const out: Turn[] = [];
  let cur: Turn | null = null;
  for (const m of messages) {
    if (m.role === "user") {
      cur = { ...newTurn(agent, m.text), status: "done", restored: true };
      out.push(cur);
    } else if (cur && m.role === "assistant") {
      if (m.tool_calls.length) cur.tools.push(...m.tool_calls.map((tc) => ({ ...tc, status: "ok" as const })));
      else cur.final = { type: "final", text: m.text, citations: m.citations ?? [], data: m.data ?? null };
    } else if (cur && m.role === "tool") {
      const row = cur.tools.find((r) => r.id === m.tool_call_id);
      if (row) {
        try {
          row.result = JSON.parse(m.text);
        } catch {
          row.result = m.text;
        }
        cur.seen.push(...seenIn(row.name, row.result).filter((s) => !cur!.seen.some((x) => x.id === s.id)));
      }
    }
  }
  return out;
}
