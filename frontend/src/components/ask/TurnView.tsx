"use client";

import { Check, CircleAlert, Copy, RotateCcw, ShieldCheck, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Reply, Roast, Turn } from "@/lib/agent";
import { api } from "@/lib/api";
import { Markdown } from "../Markdown";
import { Marquee } from "../studio/Marquee";
import { Spinner } from "../ui";
import { AGENTS } from "./theme";
import { summary, ToolResult } from "./ToolResult";

function seconds(ms: number) {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function useElapsed(running: boolean, started: number) {
  const [now, setNow] = useState(started);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [running]);
  return Math.max(0, Math.round((now - started) / 1000));
}

/** The tilted card naming what is being read, set like a "now playing" sleeve. */
function NowReading({ scope, agent, elapsed }: { scope: string; agent: Turn["agent"]; elapsed: number }) {
  const a = AGENTS[agent];
  return (
    <div className={`${a.bg} text-night shadow-lift w-full max-w-[19rem] shrink-0 -rotate-2 rounded-[22px] p-5`}>
      <div className="flex items-center justify-between text-[13px] font-semibold">
        <span className="flex items-center gap-2">
          <span className="bg-night size-2 animate-pulse rounded-full motion-reduce:animate-none" />
          Now reading
        </span>
        <span className="tabular font-mono">{elapsed}s</span>
      </div>
      <p className="display mt-3 text-[34px] leading-[0.95] break-words">{scope}</p>
      <p className="mt-2 text-[14px]">{a.name}</p>
    </div>
  );
}

function ToolRows({ turn }: { turn: Turn }) {
  if (!turn.tools.length) return null;
  return (
    <ol aria-label="What the agent did" className="border-line grid border-t">
      {turn.tools.map((r, i) => (
        <li key={r.id} className="border-line rise grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3 border-b py-3">
          <span
            className={`mt-0.5 grid size-6 place-items-center rounded-full text-[11px] font-bold ${
              r.status === "running" ? "border-line-strong border" : r.status === "ok" ? "bg-night-3 text-cream-2" : "bg-alarm text-night"
            }`}
          >
            {r.status === "running" ? <Spinner className="size-3" /> : r.status === "ok" ? <span className="tabular">{i + 1}</span> : <X className="size-3.5" aria-hidden />}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
              <p className="text-[15px] text-cream">
                {toolLabel(r.name)}
                {typeof r.args.query === "string" && <span className="text-cream-2"> &ldquo;{r.args.query}&rdquo;</span>}
                {typeof r.args.participant === "string" && r.name !== "search_messages" && (
                  <span className="text-cream-2"> {r.args.participant}</span>
                )}
              </p>
              {r.ms !== undefined && <span className="text-cream-3 tabular font-mono text-[12px]">{seconds(r.ms)}</span>}
            </div>
            {r.status !== "running" && r.result !== undefined && (
              <>
                <p className={`text-sm ${r.status === "failed" ? "text-alarm" : "text-cream-3"}`}>{summary(r.name, r.result)}</p>
                <div className="mt-2 empty:hidden">
                  <ToolResult name={r.name} result={r.result} />
                </div>
              </>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

const LABELS: Record<string, string> = {
  search_messages: "Searched",
  get_chat_stats: "Counted the chat",
  get_reply_graph: "Mapped replies",
  get_mood_series: "Read the mood",
  get_timeline: "Read the timeline",
  get_persona: "Read the persona of",
  get_media: "Opened media",
  get_messages_around: "Read around a message",
  list_chats: "Listed chats",
  list_participants: "Listed people",
  get_inside_jokes: "Looked up inside jokes",
};
const toolLabel = (n: string) => LABELS[n] ?? n.replace(/_/g, " ");

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text).catch(() => {});
        setDone(true);
        setTimeout(() => setDone(false), 2500);
      }}
      className="border-night/25 hover:bg-night hover:text-cream inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm font-semibold transition-colors"
    >
      {done ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
      {done ? "Copied" : "Copy"}
    </button>
  );
}

function Wave() {
  return (
    <span aria-hidden className="flex h-4 items-end gap-[3px]">
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className="wave-bar bg-cream w-[3px] rounded-full" style={{ animationDelay: `${i * 120}ms` }} />
      ))}
    </span>
  );
}

/** Reads a roast aloud: Gemini's voice from the API, the browser's voice (en-IN when available) if that fails. */
function SpeakButton({ pid, text }: { pid: number; text: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const audio = useRef<HTMLAudioElement | null>(null);
  const url = useRef<string | null>(null);
  useEffect(
    () => () => {
      audio.current?.pause();
      if (url.current) URL.revokeObjectURL(url.current);
      window.speechSynthesis?.cancel();
    },
    [],
  );

  function browserVoice() {
    const s = window.speechSynthesis;
    if (!s) return setState("idle");
    s.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.voice = s.getVoices().find((v) => v.lang === "en-IN") ?? null;
    u.onend = u.onerror = () => setState("idle");
    s.speak(u);
    setState("playing");
  }

  async function play() {
    if (state !== "idle") {
      audio.current?.pause();
      window.speechSynthesis?.cancel();
      return setState("idle");
    }
    setState("loading");
    try {
      if (!url.current) url.current = URL.createObjectURL(await api.speak(pid, text));
      const a = new Audio(url.current);
      audio.current = a;
      a.onended = a.onerror = () => setState("idle");
      await a.play();
      setState("playing");
    } catch {
      browserVoice();
    }
  }

  return (
    <button
      aria-label={state === "idle" ? "Read aloud" : "Stop reading"}
      onClick={play}
      className="bg-night text-cream hover:bg-night-3 grid size-10 shrink-0 place-items-center rounded-full transition-colors"
    >
      {state === "loading" ? <Spinner /> : state === "playing" ? <Wave /> : <Volume2 aria-hidden className="size-4" />}
    </button>
  );
}

function Roasts({ pid, items, onCite }: { pid: number; items: Roast[]; onCite: (id: number) => void }) {
  return (
    <ol className="grid gap-4">
      {items.map((r, i) => (
        <li
          key={i}
          className={`${["bg-pink", "bg-cream", "bg-lime"][i % 3]} ${["-rotate-1", "rotate-1", "-rotate-[0.5deg]"][i % 3]} text-night rise rounded-[22px] p-5 sm:p-6`}
          style={{ animationDelay: `${i * 90}ms` }}
        >
          <div className="flex items-start gap-4">
            <span className="display text-[40px] leading-none">{i + 1}</span>
            <p className="flex-1 text-[19px] leading-snug font-semibold">{r.text}</p>
            <SpeakButton pid={pid} text={r.text} />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px]">
            {r.status === "rewritten" && (
              <span className="bg-night/10 inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold">
                <ShieldCheck aria-hidden className="size-3.5" /> Rewritten to stay fair
              </span>
            )}
            {r.evidence_ids.map((id, k) => (
              <button
                key={id}
                onClick={() => onCite(id)}
                className="bg-night text-cream hover:bg-night-3 rounded-full px-2.5 py-1 font-semibold transition-colors"
              >
                Receipt {k + 1}
              </button>
            ))}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Replies({ items }: { items: Reply[] }) {
  return (
    <ol className="grid gap-3">
      {items.map((r, i) => (
        <li key={i} className="bg-cream text-night rise rounded-[22px] p-5" style={{ animationDelay: `${i * 70}ms` }}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="bg-night text-cream rounded-full px-2.5 py-1 text-[12px] font-semibold">{r.tone}</span>
            <CopyButton text={r.text} />
          </div>
          <p className="mt-3 text-[19px] leading-snug font-semibold">{r.text}</p>
          <p className="mt-2 text-[14px] text-night/70">{r.why}</p>
        </li>
      ))}
    </ol>
  );
}

export function TurnView({
  pid,
  turn,
  scope,
  onCite,
  activeCite,
  onRetry,
}: {
  pid: number;
  turn: Turn;
  scope: string;
  onCite: (id: number) => void;
  activeCite: number | null;
  onRetry: () => void;
}) {
  const a = AGENTS[turn.agent];
  const running = turn.status === "running";
  const elapsed = useElapsed(running, turn.started);
  const f = turn.final;
  const verified = f ? new Set(f.citations.map((c) => c.id)) : undefined;
  const ref = useRef<HTMLElement>(null);

  return (
    <article ref={ref} aria-label={turn.question} className="scroll-mt-24">
      <header className="flex items-start gap-4">
        <span className={`${a.bg} text-night mt-1 shrink-0 rounded-full px-3 py-1 text-[13px] font-bold`}>{a.short}</span>
        <h2 className="text-[22px] leading-snug font-semibold text-cream sm:text-[26px]">{turn.question}</h2>
      </header>

      {running && (
        <div className="mt-6 overflow-hidden rounded-[24px]">
          <Marquee items={turn.actions.length ? turn.actions : ["Starting"]} tone={a.band} seconds={22} size={20} />
        </div>
      )}

      <div className={`mt-6 ${running ? "flex flex-col gap-6 lg:flex-row lg:items-start" : ""}`}>
        {running && <NowReading scope={scope} agent={turn.agent} elapsed={elapsed} />}
        <div className="min-w-0 flex-1">
          {turn.restored && turn.tools.length > 0 ? (
            <details className="text-cream-3 text-sm">
              <summary className="cursor-pointer hover:text-cream">
                {turn.tools.length} step{turn.tools.length === 1 ? "" : "s"} taken
              </summary>
              <div className="mt-3">
                <ToolRows turn={turn} />
              </div>
            </details>
          ) : (
            <ToolRows turn={turn} />
          )}
          {running && !turn.tools.length && !turn.draft && (
            <p className="text-cream-3 flex items-center gap-2 text-sm" aria-live="polite">
              <Spinner /> {turn.actions.at(-1) ?? "Starting"}
            </p>
          )}
          {turn.checking && (
            <p className="text-cream-2 mt-4 flex items-center gap-2 text-sm" aria-live="polite">
              <Spinner /> {turn.checking === "safety" ? "Checking every roast is about habits, not identity" : "Putting the answer together"}
            </p>
          )}
        </div>
      </div>

      {running && turn.draft && (
        <div className="mt-6" aria-live="off">
          <Markdown text={turn.draft} onCite={onCite} active={activeCite} />
        </div>
      )}

      {f && (
        <div className="mt-6">
          {f.refused ? (
            <p className="border-pink bg-night-2 flex items-start gap-3 rounded-[20px] border px-5 py-4 text-[17px] text-cream">
              <ShieldCheck aria-hidden className="text-pink mt-0.5 size-5 shrink-0" /> {f.text}
            </p>
          ) : f.data && "roasts" in f.data && f.data.roasts.length ? (
            <>
              <p className="display mb-5 text-[40px] text-cream">{f.data.target}, roasted</p>
              <Roasts pid={pid} items={f.data.roasts} onCite={onCite} />
              {f.data.dropped > 0 && (
                <p className="text-cream-3 mt-4 text-sm">
                  {f.data.dropped} roast{f.data.dropped === 1 ? " was" : "s were"} dropped by the safety check.
                </p>
              )}
            </>
          ) : f.data && "replies" in f.data && f.data.replies.length ? (
            <Replies items={f.data.replies} />
          ) : (
            <Markdown text={f.text} onCite={onCite} verified={verified} active={activeCite} />
          )}
          <footer className="text-cream-3 mt-6 flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px]">
            {f.citations.length > 0 && (
              <span className="flex items-center gap-1.5">
                <Check aria-hidden className="text-lime size-4" /> {f.citations.length} cited message
                {f.citations.length === 1 ? "" : "s"}, each checked
              </span>
            )}
            {!!f.dropped_citations && <span>{f.dropped_citations} unverifiable citation{f.dropped_citations === 1 ? "" : "s"} removed</span>}
            {f.model && <span className="font-mono">{f.model}</span>}
            {f.duration_ms !== undefined && <span className="tabular font-mono">{seconds(f.duration_ms)}</span>}
          </footer>
        </div>
      )}

      {turn.status === "error" && (
        <div role="alert" className="border-alarm mt-6 flex flex-wrap items-center justify-between gap-4 rounded-[20px] border px-5 py-4">
          <p className="text-alarm flex items-center gap-2 text-[15px]">
            <CircleAlert aria-hidden className="size-5 shrink-0" /> {turn.error}
          </p>
          <button onClick={onRetry} className="inline-flex items-center gap-1.5 text-[15px] font-semibold text-cream underline">
            <RotateCcw aria-hidden className="size-4" /> Try again
          </button>
        </div>
      )}
      {turn.status === "stopped" && <p className="text-cream-3 mt-4 text-sm">Stopped.</p>}
    </article>
  );
}
