"use client";

import { ArrowLeft, FileText, ImageIcon, Mic, Video } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Msg, Seen, Turn } from "@/lib/agent";
import { api } from "@/lib/api";
import { formatDay } from "@/lib/format";
import { Spinner } from "../ui";

const MEDIA_ICON: Record<string, typeof Mic> = { voice: Mic, audio: Mic, image: ImageIcon, video: Video, document: FileText };
const MEDIA_LABEL: Record<string, string> = { voice: "Voice note", audio: "Audio", image: "Photo", video: "Video", document: "Document" };

function time(ts: string) {
  return ts.slice(11, 16);
}

/** One message as a chat bubble. The user's own messages sit on the right in lime, like WhatsApp. */
function Bubble({ m, me, pid, focus }: { m: Msg; me: boolean; pid: number; focus?: boolean }) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (focus) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focus]);
  if (m.kind === "system")
    return (
      <li className="text-cream-3 py-1 text-center text-[13px]">
        {m.text} <span className="tabular font-mono">{time(m.ts)}</span>
      </li>
    );
  const Icon = MEDIA_ICON[m.kind];
  return (
    <li ref={ref} className={`flex ${me ? "justify-end" : ""}`}>
      <figure className={`max-w-[88%] ${focus ? "flash rounded-2xl" : ""}`}>
        {!me && <figcaption className="text-cream-3 mb-1 px-1 text-[12px] font-semibold">{m.sender}</figcaption>}
        <div className={`rounded-2xl px-3.5 py-2.5 text-[15px] leading-snug ${me ? "bg-lime text-night rounded-br-md" : "bg-night-3 rounded-bl-md text-cream"}`}>
          {Icon && (
            <p className={`mb-1 flex items-center gap-1.5 text-[12px] font-semibold ${me ? "text-night/70" : "text-cream-2"}`}>
              <Icon aria-hidden className="size-3.5" /> {MEDIA_LABEL[m.kind]}
            </p>
          )}
          {m.kind === "image" && m.media?.status === "done" && (
            // eslint-disable-next-line @next/next/no-img-element -- served by the API, size unknown
            <img src={api.mediaUrl(pid, m.media.id)} alt={m.media.result ?? "Photo from the chat"} className="mb-2 max-h-56 rounded-xl" loading="lazy" />
          )}
          {m.kind === "voice" && m.media?.status === "done" && (
            <audio controls preload="none" src={api.mediaUrl(pid, m.media.id)} className="mb-2 h-9 w-full max-w-[16rem]" />
          )}
          {m.text && <p className="break-words whitespace-pre-wrap">{m.text}</p>}
          {m.media?.result && (
            <p className={`mt-1 text-[13px] italic ${me ? "text-night/70" : "text-cream-2"}`}>&ldquo;{m.media.result}&rdquo;</p>
          )}
          {m.kind === "deleted" && <p className="italic opacity-70">This message was deleted</p>}
          <p className={`mt-1 text-right font-mono text-[11px] ${me ? "text-night/60" : "text-cream-3"}`}>
            {time(m.ts)}
            {m.edited && " edited"}
          </p>
        </div>
      </figure>
    </li>
  );
}

/** The opened message with five messages either side. */
export function Context({
  pid,
  id,
  meId,
  onBack,
  backLabel = "All evidence",
}: {
  pid: number;
  id: number;
  meId: number | null;
  onBack: () => void;
  backLabel?: string;
}) {
  const [data, setData] = useState<{ message: Msg; before: Msg[]; after: Msg[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .message(pid, id, 5)
      .then((d) => live && setData(d))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [pid, id]);
  return (
    <div>
      <div className="bg-night sticky -top-6 z-10 -mx-5 px-5 pt-6 pb-3">
        <button onClick={onBack} className="text-cream-2 hover:text-cream inline-flex items-center gap-1.5 text-sm font-semibold">
          <ArrowLeft aria-hidden className="size-4" /> {backLabel}
        </button>
      </div>
      {error && <p className="text-alarm mt-4 text-sm">{error}</p>}
      {!data && !error && (
        <p className="text-cream-3 mt-6 flex items-center gap-2 text-sm">
          <Spinner /> Opening the message
        </p>
      )}
      {data && (
        <>
          <p className="text-cream-3 mt-4 text-sm">{formatDay(data.message.ts)}</p>
          <ul className="mt-3 grid gap-2.5">
            {[...data.before, data.message, ...data.after].map((m) => (
              <Bubble key={m.id} m={m} me={meId !== null && m.participant_id === meId} pid={pid} focus={m.id === id} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function SeenRow({ s, onOpen, cited }: { s: Seen; onOpen: () => void; cited: number | null }) {
  return (
    <li>
      <button onClick={onOpen} className="hover:bg-night-3 rise w-full rounded-2xl p-3 text-left transition-colors">
        <span className="flex items-baseline justify-between gap-3">
          <span className="truncate text-[13px] font-semibold text-cream">{s.sender}</span>
          <span className="text-cream-3 tabular shrink-0 font-mono text-[11px]">{s.ts.slice(0, 10)}</span>
        </span>
        <span className="text-cream-2 mt-0.5 line-clamp-2 block text-[14px] leading-snug">{s.text}</span>
        {cited !== null && <span className="cite tabular mt-1.5 !ml-0">{cited}</span>}
      </button>
    </li>
  );
}

/** The right-hand panel: what the agent read this turn, cited messages first. */
export function Evidence({
  pid,
  turn,
  open,
  onOpen,
  meId,
}: {
  pid: number;
  turn: Turn | null;
  open: number | null;
  onOpen: (id: number | null) => void;
  meId: number | null;
}) {
  if (open !== null) return <Context pid={pid} id={open} meId={meId} onBack={() => onOpen(null)} />;
  if (!turn)
    return (
      <div>
        <h2 className="text-[17px] font-semibold text-cream">Evidence</h2>
        <p className="text-cream-3 mt-2 text-[15px]">
          The messages an agent reads show up here as it works. Tap one to read the conversation around it.
        </p>
      </div>
    );
  const cited = turn.final?.citations ?? [];
  const order = cited.map((c) => c.id);
  const rest = turn.seen.filter((s) => !order.includes(s.id));
  const citedSeen: Seen[] = cited.map((c) => ({
    id: c.id,
    ts: c.ts,
    chat: c.chat_title ?? null,
    sender: c.sender ?? "",
    text: c.text || (c.media?.result ? `"${c.media.result}"` : `(${c.kind})`),
  }));
  return (
    <div>
      <h2 className="flex items-baseline justify-between text-[17px] font-semibold text-cream">
        Evidence
        <span className="text-cream-3 text-sm font-normal">
          {turn.seen.length || cited.length ? `${Math.max(turn.seen.length, cited.length)} read` : turn.status === "running" ? "reading" : "none"}
        </span>
      </h2>
      {citedSeen.length > 0 && (
        <>
          <p className="text-lime mt-4 px-3 text-[13px] font-semibold">Cited in the answer</p>
          <ul className="mt-1 grid">
            {citedSeen.map((s, i) => (
              <SeenRow key={s.id} s={s} onOpen={() => onOpen(s.id)} cited={i + 1} />
            ))}
          </ul>
        </>
      )}
      {rest.length > 0 && (
        <>
          <p className="text-cream-3 mt-4 px-3 text-[13px] font-semibold">{citedSeen.length ? "Also read" : "Read so far"}</p>
          <ul className="mt-1 grid">
            {rest.slice(0, 24).map((s) => (
              <SeenRow key={s.id} s={s} onOpen={() => onOpen(s.id)} cited={null} />
            ))}
          </ul>
        </>
      )}
      {!citedSeen.length && !rest.length && (
        <p className="text-cream-3 mt-4 flex items-center gap-2 text-sm">
          {turn.status === "running" && <Spinner />}
          {turn.status === "running" ? "Messages show up here when the agent searches or reads them." : "This answer used counts, not individual messages."}
        </p>
      )}
    </div>
  );
}
