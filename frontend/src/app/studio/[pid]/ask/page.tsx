"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, BookOpen, Plus, Square, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Evidence } from "@/components/ask/Evidence";
import { AGENTS, ORDER } from "@/components/ask/theme";
import { TurnView } from "@/components/ask/TurnView";
import { useStudio } from "@/components/studio/StudioProvider";
import { Button } from "@/components/ui";
import { applyEvent, newTurn, streamAgent, type AgentKey, type ScopeType, type Tone, type Turn } from "@/lib/agent";
import { ApiError } from "@/lib/api";
import type { Chat, Participant } from "@/lib/types";

const first = (n: string) => (n.startsWith("+") ? n : n.split(" ")[0]);

/** Starter questions per agent, written from the chat actually in scope. */
function starters(agent: AgentKey, chat: Chat | null, person: Participant | null, chats: Chat[]): string[] {
  const group = chat?.kind === "group" ? chat : chats.find((c) => c.kind === "group") ?? null;
  const direct = chat?.kind === "direct" ? chat : chats.find((c) => c.kind === "direct") ?? null;
  const who = person ? first(person.name) : null;
  switch (agent) {
    case "analyzer":
      return who
        ? [`How does ${who} usually talk in the chats?`, `Who does ${who} reply to most?`, `When is ${who} most active?`]
        : [
            group ? `Who drives ${group.title}, and how did the mood change over the year?` : "Who drives the conversation?",
            "Who is the night owl, and who went silent for months?",
            "Who replies to whom the most?",
          ];
    case "roaster":
      return who
        ? [`Roast ${who}`, `Roast ${who}'s typing style`, `Roast ${who}'s timing`]
        : ["Roast the voice-note king", "Roast the night owl", "Roast whoever starts every plan"];
    case "recall":
      return [
        group ? `What trips did ${group.title} plan, and who backed out?` : "What trips did we plan?",
        "Who forgot the tickets?",
        direct ? `Did I ever pay ${direct.title} back?` : "Who owes whom money?",
      ];
    case "reply":
      return [
        direct ? `What should I reply to ${direct.title}'s last message?` : "What should I reply to the last message?",
        "Give me a funny reply to the group's plan",
        "Help me say no to the next trip, nicely",
      ];
  }
}

function ScopePicker({
  chats,
  people,
  scope,
  onChange,
}: {
  chats: Chat[];
  people: Participant[];
  scope: { type: ScopeType; id: number | null };
  onChange: (s: { type: ScopeType; id: number | null }) => void;
}) {
  const value = scope.type === "project" ? "project" : `${scope.type}:${scope.id}`;
  return (
    <label className="flex items-center gap-2">
      <span className="text-cream-3 text-sm">Reading</span>
      <select
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "project") onChange({ type: "project", id: null });
          else {
            const [t, id] = v.split(":");
            onChange({ type: t as ScopeType, id: Number(id) });
          }
        }}
        className="border-line-strong bg-night-2 hover:border-cream h-9 max-w-[15rem] rounded-full border px-3.5 text-[15px] font-semibold text-cream outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lime"
      >
        <option value="project">Every chat</option>
        <optgroup label="One chat">
          {chats.map((c) => (
            <option key={c.id} value={`chat:${c.id}`}>
              {c.title}
            </option>
          ))}
        </optgroup>
        <optgroup label="One person">
          {people.slice(0, 40).map((p) => (
            <option key={p.id} value={`participant:${p.id}`}>
              {p.name}
              {p.is_me ? " (you)" : ""}
            </option>
          ))}
        </optgroup>
      </select>
    </label>
  );
}

const TONES: { key: Tone; label: string }[] = [
  { key: "wholesome", label: "Wholesome" },
  { key: "spicy", label: "Spicy" },
  { key: "savage", label: "Savage" },
];

export default function AskPage() {
  const { project, pid, people } = useStudio();
  const search = useSearchParams();
  const router = useRouter();
  const chats = useMemo(() => project?.chats ?? [], [project]);

  const initialAgent = (ORDER as string[]).includes(search.get("agent") ?? "") ? (search.get("agent") as AgentKey) : "analyzer";
  const initialChat = Number(search.get("chat")) || null;
  const [agent, setAgent] = useState<AgentKey>(initialAgent);
  const [scope, setScope] = useState<{ type: ScopeType; id: number | null }>(
    initialChat ? { type: "chat", id: initialChat } : { type: "project", id: null },
  );
  const [tone, setTone] = useState<Tone>("spicy");
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [thread, setThread] = useState<number | null>(null);
  const [openMsg, setOpenMsg] = useState<number | null>(null);
  const [sheet, setSheet] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const autoAsked = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const chat = scope.type === "chat" ? chats.find((c) => c.id === scope.id) ?? null : null;
  const person = scope.type === "participant" ? people.find((p) => p.id === scope.id) ?? null : null;
  const scopeName = chat?.title ?? person?.name ?? project?.name ?? "";
  const me = people.find((p) => p.is_me) ?? null;
  const running = turns.some((t) => t.status === "running");
  const last = turns.at(-1) ?? null;
  const a = AGENTS[agent];

  const reset = useCallback(() => {
    abort.current?.abort();
    setTurns([]);
    setThread(null);
    setOpenMsg(null);
  }, []);

  const ask = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || pid === null || running) return;
      const turn = newTurn(agent, q);
      setTurns((ts) => [...ts, turn]);
      setText("");
      setOpenMsg(null);
      const ctl = new AbortController();
      abort.current = ctl;
      const fold = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.key === turn.key ? fn(t) : t)));
      try {
        for await (const ev of streamAgent(
          pid,
          {
            agent,
            message: q,
            scope_type: scope.type,
            scope_id: scope.id,
            thread_id: thread,
            options: agent === "roaster" ? { tone } : agent === "reply" ? { style_of: "me" } : {},
          },
          ctl.signal,
        )) {
          if (ev.type === "thread") setThread(ev.thread_id);
          else fold((t) => applyEvent(t, ev));
        }
        fold((t) => (t.status === "running" ? { ...t, status: "error", error: "The answer stopped before it finished." } : t));
      } catch (e) {
        if (ctl.signal.aborted) fold((t) => ({ ...t, status: "stopped", tools: t.tools.map((r) => (r.status === "running" ? { ...r, status: "failed" } : r)) }));
        else fold((t) => ({ ...t, status: "error", error: e instanceof ApiError && e.offline ? "The server isn't answering." : e instanceof Error ? e.message : String(e) }));
      }
    },
    [agent, pid, running, scope, thread, tone],
  );

  // A question handed over from a chat's first read runs once, then leaves the URL.
  useEffect(() => {
    const q = search.get("q");
    if (!q || autoAsked.current || pid === null || !project) return;
    autoAsked.current = true;
    router.replace(`/studio/${pid}/ask${initialChat ? `?chat=${initialChat}` : ""}`, { scroll: false });
    void ask(q);
  }, [search, pid, project, router, initialChat, ask]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns.length, last?.status]);

  const openCite = useCallback((id: number) => {
    setOpenMsg(id);
    setSheet(true);
  }, []);

  if (!project || pid === null)
    return (
      <div className="mx-auto max-w-6xl px-6 py-14 lg:px-12">
        <div className="skeleton h-12 w-72 rounded-2xl" />
      </div>
    );

  if (!chats.length)
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 lg:px-12">
        <h1 className="display text-[56px] text-cream">Nothing to read yet</h1>
        <p className="text-cream-2 mt-3 text-[17px]">Upload a chat first, then come back and ask.</p>
        <Button className="mt-6" onClick={() => router.push(`/studio/${pid}`)}>
          Add a chat
        </Button>
      </div>
    );

  const evidence = <Evidence pid={pid} turn={last} open={openMsg} onOpen={setOpenMsg} meId={me?.id ?? null} />;

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_25rem]">
      <div className="flex min-h-[calc(100dvh-3.5rem)] min-w-0 flex-col lg:min-h-dvh">
        {/* Agent tabs and scope */}
        <div className="border-line bg-night sticky top-14 z-20 border-b px-5 py-3 lg:top-0 lg:px-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div role="tablist" aria-label="Agent" className="flex gap-1.5 overflow-x-auto">
              {ORDER.map((k) => {
                const on = k === agent;
                return (
                  <button
                    key={k}
                    role="tab"
                    aria-selected={on}
                    disabled={running}
                    onClick={() => {
                      if (k === agent) return;
                      setAgent(k);
                      reset();
                    }}
                    className={`h-9 shrink-0 rounded-full px-4 text-[15px] font-semibold transition-colors ${
                      on ? `${AGENTS[k].bg} text-night` : "text-cream-2 hover:text-cream hover:bg-night-3"
                    }`}
                  >
                    {AGENTS[k].name}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-2">
              <ScopePicker
                chats={chats}
                people={people}
                scope={scope}
                onChange={(s) => {
                  setScope(s);
                  reset();
                }}
              />
              {turns.length > 0 && (
                <Button variant="ghost" size="sm" onClick={reset} disabled={running} aria-label="New conversation">
                  <Plus aria-hidden className="size-4" /> New
                </Button>
              )}
            </div>
          </div>
        </div>

        <div className="flex-1 px-5 py-8 lg:px-10">
          {turns.length === 0 ? (
            <section aria-labelledby="ask-title" className="mx-auto max-w-3xl pt-6">
              <p className={`${a.text} text-[15px] font-semibold`}>{a.name}</p>
              <h1 id="ask-title" className="display mt-2 text-[56px] text-cream sm:text-[76px]">
                {agent === "roaster" ? "Who's getting roasted?" : agent === "reply" ? "What do you need to say?" : agent === "recall" ? "What are you trying to remember?" : `Ask about ${scopeName}`}
              </h1>
              <p className="text-cream-2 mt-3 max-w-[54ch] text-[17px]">{a.job}</p>
              <ul className="border-line mt-10 border-t">
                {starters(agent, chat, person, chats).map((q) => (
                  <li key={q} className="border-line border-b">
                    <button onClick={() => void ask(q)} className="group flex w-full items-center justify-between gap-4 py-4 text-left">
                      <span className="text-[19px] text-cream group-hover:underline group-hover:decoration-line-strong">{q}</span>
                      <ArrowUp aria-hidden className="text-cream-3 size-5 shrink-0 rotate-45 transition-transform group-hover:text-cream" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-16">
              {turns.map((t) => (
                <TurnView
                  key={t.key}
                  turn={t}
                  scope={scopeName}
                  onCite={openCite}
                  activeCite={openMsg}
                  onRetry={() => {
                    setTurns((ts) => ts.filter((x) => x.key !== t.key));
                    void ask(t.question);
                  }}
                />
              ))}
              <div ref={bottom} />
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="bg-night sticky bottom-0 z-20 px-5 pt-2 pb-5 lg:px-10">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void ask(text);
            }}
            className="border-line-strong bg-night-2 focus-within:border-cream mx-auto max-w-3xl rounded-[28px] border p-2 transition-colors"
          >
            {agent === "roaster" && (
              <div role="radiogroup" aria-label="Roast tone" className="flex gap-1 px-2 pt-1 pb-2">
                {TONES.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    role="radio"
                    aria-checked={tone === t.key}
                    onClick={() => setTone(t.key)}
                    className={`h-8 rounded-full px-3.5 text-sm font-semibold transition-colors ${
                      tone === t.key ? "bg-pink text-night" : "text-cream-2 hover:text-cream hover:bg-night-3"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2">
              <label htmlFor="ask" className="sr-only">
                Ask the {a.name}
              </label>
              <textarea
                id="ask"
                ref={input}
                rows={1}
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void ask(text);
                  }
                }}
                maxLength={4000}
                placeholder={agent === "roaster" ? "Roast Rohan's voice notes" : `Ask about ${scopeName}`}
                className="placeholder:text-cream-3 max-h-40 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-[17px] text-cream outline-none"
              />
              {running ? (
                <button
                  type="button"
                  onClick={() => abort.current?.abort()}
                  aria-label="Stop"
                  className="bg-cream text-night grid size-11 shrink-0 place-items-center rounded-full"
                >
                  <Square aria-hidden className="size-4 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!text.trim()}
                  aria-label="Ask"
                  className={`${a.bg} text-night grid size-11 shrink-0 place-items-center rounded-full transition-opacity disabled:opacity-40`}
                >
                  <ArrowUp aria-hidden className="size-5" />
                </button>
              )}
            </div>
          </form>
          <button
            onClick={() => setSheet(true)}
            className="text-cream-2 hover:text-cream mx-auto mt-2 flex items-center gap-1.5 text-sm font-semibold lg:hidden"
          >
            <BookOpen aria-hidden className="size-4" /> Evidence
            {last && last.seen.length > 0 && <span className="tabular">({last.seen.length})</span>}
          </button>
        </div>
      </div>

      {/* Evidence: a column on desktop, a sheet on phones */}
      <aside aria-label="Evidence" className="border-line sticky top-0 hidden h-dvh overflow-y-auto border-l px-5 py-6 lg:block">
        {evidence}
      </aside>
      <AnimatePresence>
        {sheet && (
          <div className="lg:hidden">
            <motion.div className="bg-scrim fixed inset-0 z-40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSheet(false)} />
            <motion.div
              role="dialog"
              aria-label="Evidence"
              className="bg-night border-line fixed inset-x-0 bottom-0 z-50 max-h-[80dvh] overflow-y-auto rounded-t-[28px] border-t px-5 pt-5 pb-8"
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            >
              <button
                onClick={() => setSheet(false)}
                aria-label="Close evidence"
                className="hover:bg-night-3 absolute top-3 right-3 grid size-10 place-items-center rounded-full"
              >
                <X aria-hidden className="size-5" />
              </button>
              {evidence}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
