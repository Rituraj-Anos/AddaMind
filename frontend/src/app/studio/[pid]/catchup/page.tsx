"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Check, Copy, MessageSquareReply, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Context } from "@/components/ask/Evidence";
import { useStudio } from "@/components/studio/StudioProvider";
import { Button, Spinner } from "@/components/ui";
import type { Msg } from "@/lib/agent";
import { api } from "@/lib/api";
import { formatCount, formatDay, parseTs, plural } from "@/lib/format";
import type { CatchupCounts, CatchupMode, CatchupRead } from "@/lib/types";

const MODES: { key: CatchupMode; label: string }[] = [
  { key: "auto", label: "Since I last wrote" },
  { key: "day", label: "The chat's last day" },
  { key: "upload", label: "Since the last upload" },
  { key: "time", label: "Pick a time" },
];
const MEDIA: Record<string, string> = { voice: "voice note", image: "photo", video: "video", document: "document", sticker: "sticker", audio: "audio file" };

const clock = (ts: string) => ts.slice(11, 16);
/** "Tue 14 Mar, 21:04" style, short enough for a chip. */
function when(ts: string) {
  return `${parseTs(ts).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${clock(ts)}`;
}

function CopyReply({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text).catch(() => {});
        setDone(true);
        setTimeout(() => setDone(false), 2000);
      }}
      className="border-line-strong hover:border-lime group flex w-full items-start justify-between gap-3 rounded-2xl border px-4 py-3 text-left transition-colors"
    >
      <span className="text-[16px] leading-snug text-cream">{text}</span>
      <span className="text-cream-3 group-hover:text-lime mt-0.5 inline-flex shrink-0 items-center gap-1 text-[13px] font-semibold">
        {done ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
        {done ? "Copied" : "Copy"}
      </span>
    </button>
  );
}

function Quote({ m }: { m: Msg }) {
  const media = m.media?.result ? `${MEDIA[m.kind] ?? m.kind}: \u201c${m.media.result}\u201d` : null;
  return (
    <div className="bg-night-3 rounded-2xl rounded-bl-md px-4 py-3">
      <p className="flex items-baseline justify-between gap-3">
        <span className="text-[14px] font-semibold text-cream">{m.sender}</span>
        <span className="text-cream-3 tabular font-mono text-[12px]">{when(m.ts)}</span>
      </p>
      {m.text && <p className="mt-1 text-[17px] leading-snug break-words text-cream">{m.text}</p>}
      {media && <p className="text-cream-2 mt-1 text-[14px] italic">{media}</p>}
    </div>
  );
}

function Receipts({ ids, onOpen }: { ids: number[]; onOpen: (id: number) => void }) {
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((id, i) => (
        <button key={id} onClick={() => onOpen(id)} className="cite tabular" aria-label={`Open message ${i + 1}`}>
          {i + 1}
        </button>
      ))}
    </span>
  );
}

function Numbers({ c }: { c: CatchupCounts }) {
  const media = Object.entries(c.media).filter(([, n]) => n > 0);
  return (
    <div className="flex flex-wrap items-end gap-x-14 gap-y-6">
      <div>
        <p className="display text-lime text-[96px] leading-[0.85] sm:text-[128px]">{formatCount(c.unread)}</p>
        <p className="text-cream-2 mt-2 text-[17px]">
          {c.unread === 1 ? "message" : "messages"} {c.label}
          {c.first_ts && c.last_ts && (
            <>
              , {when(c.first_ts)} to {when(c.last_ts)}
            </>
          )}
        </p>
      </div>
      {c.unread > 0 && (
        <dl className="flex flex-wrap gap-x-10 gap-y-4 pb-2">
          <div>
            <dt className="text-cream-3 text-[14px]">People talking</dt>
            <dd className="display text-[44px] leading-none text-cream">{c.people}</dd>
          </div>
          <div>
            <dt className="text-cream-3 text-[14px]">Mention you</dt>
            <dd className={`display text-[44px] leading-none ${c.mentions.length ? "text-pink" : "text-cream"}`}>{c.mentions.length}</dd>
          </div>
          {media.length > 0 && (
            <div>
              <dt className="text-cream-3 text-[14px]">Media</dt>
              <dd className="mt-1 text-[16px] text-cream">{media.map(([k, n]) => plural(n, MEDIA[k] ?? k)).join(", ")}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}

export default function CatchupPage() {
  const { project, pid, people } = useStudio();
  const search = useSearchParams();
  const router = useRouter();
  const chats = (project?.chats ?? []).filter((c) => c.status === "ready");
  const cid = Number(search.get("chat")) || [...chats].sort((a, b) => b.message_count - a.message_count)[0]?.id || null;
  const chat = chats.find((c) => c.id === cid) ?? null;
  const me = people.find((p) => p.is_me) ?? null;

  const [mode, setMode] = useState<CatchupMode>("auto");
  const [fromTs, setFromTs] = useState("");
  const [picked, setPicked] = useState(""); // the time actually asked for, set on "Read"
  const [counts, setCounts] = useState<{ key: string; c: CatchupCounts } | null>(null);
  const [read, setRead] = useState<{ key: string; r: CatchupRead | null; error: string | null } | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [marking, setMarking] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const key = `${cid}|${mode}|${mode === "time" ? picked : ""}|${attempt}`;
  const ready = mode !== "time" || picked !== "";

  useEffect(() => {
    if (pid === null || cid === null || !ready) return;
    let live = true;
    const ts = mode === "time" ? picked : undefined;
    api
      .catchup(pid, cid, mode, ts)
      .then((c) => {
        if (!live) return;
        setCounts({ key, c });
        if (c.unread === 0) return setRead({ key, r: null, error: null });
        return api.catchupDigest(pid, cid, c.mode, ts).then(
          (r) => live && setRead({ key, r, error: null }),
          (e: unknown) => live && setRead({ key, r: null, error: e instanceof Error ? e.message : String(e) }),
        );
      })
      .catch((e: unknown) => {
        if (!live) return;
        setCounts(null);
        setRead({ key, r: null, error: e instanceof Error ? e.message : String(e) });
      });
    return () => {
      live = false;
    };
  }, [pid, cid, mode, picked, ready, key]);

  async function markAll() {
    const last = counts?.c.last_message_id;
    if (pid === null || cid === null || !last) return;
    setMarking(true);
    try {
      await api.markCaughtUp(pid, cid, last);
      setMode("auto");
      setAttempt((n) => n + 1);
    } finally {
      setMarking(false);
    }
  }

  if (!project || pid === null) return <div className="skeleton m-12 h-12 w-72 rounded-2xl" />;
  if (!chat)
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 lg:px-12">
        <h1 className="display text-[56px] text-cream">Nothing to catch up on yet</h1>
        <Link href={`/studio/${pid}`} className="text-lime mt-4 inline-block font-semibold underline">
          Add a chat
        </Link>
      </div>
    );

  const c = counts?.key === key ? counts.c : null;
  const r = read?.key === key ? read : null;
  const digest = r?.r ?? null;
  const options = c?.options;

  return (
    <div className="pb-24">
      <div className="mx-auto max-w-[72rem] px-6 pt-12 lg:px-12 lg:pt-16">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h1 className="display text-[64px] text-cream sm:text-[96px]">Catch up</h1>
            <p className="text-cream-2 mt-2 max-w-[56ch] text-[17px]">
              What you missed in {chat.title}, what&rsquo;s waiting on you, and replies you can send.
            </p>
          </div>
          {chats.length > 1 && (
            <div role="tablist" aria-label="Chat" className="flex flex-wrap gap-2">
              {chats.map((x) => (
                <button
                  key={x.id}
                  role="tab"
                  aria-selected={x.id === cid}
                  onClick={() => router.replace(`/studio/${pid}/catchup?chat=${x.id}`, { scroll: false })}
                  className={`h-10 rounded-full px-5 text-[15px] font-semibold transition-colors ${
                    x.id === cid ? "bg-cream text-night" : "border-line-strong text-cream-2 hover:text-cream border"
                  }`}
                >
                  {x.title}
                </button>
              ))}
            </div>
          )}
        </div>

        <div role="radiogroup" aria-label="Count unread from" className="mt-10 flex flex-wrap items-center gap-2">
          {MODES.map((m) => {
            const off = options ? !options[m.key] : m.key === "upload";
            return (
              <button
                key={m.key}
                role="radio"
                aria-checked={mode === m.key}
                disabled={off}
                title={off ? (m.key === "upload" ? "Upload a newer export of this chat first" : "Mark who you are on the chats page first") : undefined}
                onClick={() => setMode(m.key)}
                className={`h-10 rounded-full px-5 text-[15px] font-semibold transition-colors disabled:opacity-40 ${
                  mode === m.key ? "bg-lime text-night on-lime" : "border-line-strong text-cream-2 hover:text-cream border"
                }`}
              >
                {m.label}
              </button>
            );
          })}
          {mode === "time" && (
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (fromTs) setPicked(fromTs);
              }}
            >
              <label className="sr-only" htmlFor="from-ts">
                Unread from
              </label>
              <input
                id="from-ts"
                type="datetime-local"
                value={fromTs}
                onChange={(e) => setFromTs(e.target.value)}
                min={chat.first_ts?.slice(0, 16).replace(" ", "T")}
                max={chat.last_ts?.slice(0, 16).replace(" ", "T")}
                className="bg-night-3 border-line-strong h-10 rounded-full border px-4 text-[15px] text-cream [color-scheme:dark]"
              />
              <Button type="submit" size="md" disabled={!fromTs}>
                Read
              </Button>
            </form>
          )}
        </div>
        {!me && (
          <p className="text-cream-3 mt-3 text-sm">
            Mark which person is you on the{" "}
            <Link href={`/studio/${pid}`} className="text-lime underline">
              chats page
            </Link>{" "}
            to count from your last message and get replies in your style.
          </p>
        )}

        <div className="mt-12">
          {!ready ? (
            <p className="text-cream-2 text-[17px]">Pick the time you stopped reading, then press Read.</p>
          ) : !c && !r?.error ? (
            <div className="skeleton h-40 w-full max-w-xl rounded-[28px]" />
          ) : r?.error && !c ? (
            <p role="alert" className="text-alarm text-[16px]">{r.error}</p>
          ) : c ? (
            <Numbers c={c} />
          ) : null}
        </div>

        {c && c.unread === 0 && (
          <div className="border-line mt-12 rounded-[28px] border p-8">
            <h2 className="display text-[48px] text-cream">You&rsquo;re all caught up</h2>
            <p className="text-cream-2 mt-2 text-[17px]">
              Nothing new {c.label}. Upload a newer export of this chat and come back to see what you missed.
            </p>
          </div>
        )}

        {c && c.unread > 0 && (
          <div className="mt-14 flex flex-col gap-16">
            {!r ? (
              <p role="status" className="text-cream-2 flex items-center gap-3 text-[17px]">
                <Spinner className="size-5" /> Reading {plural(c.unread, "message")} for you
              </p>
            ) : r.error ? (
              <div role="alert" className="flex flex-wrap items-center gap-4">
                <p className="text-alarm text-[16px]">{r.error}</p>
                <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
                  <RotateCcw aria-hidden className="size-4" /> Try again
                </Button>
              </div>
            ) : digest ? (
              <>
                {digest.tldr && (
                  <section aria-label="In short" className="bg-lime text-night on-lime rounded-[28px] p-7 sm:p-9">
                    <p className="text-[22px] leading-snug font-semibold sm:text-[26px]">{digest.tldr}</p>
                    {digest.sampled && (
                      <p className="text-night/70 mt-3 text-[14px]">So many messages that the busiest ones were read first, with everything that mentions you.</p>
                    )}
                  </section>
                )}

                <section aria-labelledby="needs-you">
                  <h2 id="needs-you" className="display text-[48px] text-cream sm:text-[64px]">
                    Waiting on you
                  </h2>
                  {digest.needs_you.length === 0 ? (
                    <p className="text-cream-2 mt-3 text-[17px]">Nobody asked you anything or mentioned you. You can just read along.</p>
                  ) : (
                    <ol className="mt-6 grid gap-6 lg:grid-cols-2">
                      {digest.needs_you.map((n) => (
                        <li key={n.message.id} className="border-line bg-night-2 flex flex-col gap-4 rounded-[28px] border p-5 sm:p-6">
                          <p className={`text-[15px] font-semibold ${n.source === "mention" ? "text-pink" : "text-lime"}`}>{n.why}</p>
                          <Quote m={n.message} />
                          {n.replies.length > 0 && (
                            <div className="flex flex-col gap-2">
                              <p className="text-cream-3 text-[14px]">Reply in your style</p>
                              {n.replies.map((t) => (
                                <CopyReply key={t} text={t} />
                              ))}
                            </div>
                          )}
                          <div className="mt-auto flex flex-wrap gap-2">
                            <Button variant="ghost" size="sm" onClick={() => setOpen(n.message.id)}>
                              Read around it
                            </Button>
                            <Link
                              href={`/studio/${pid}/ask?agent=reply&chat=${cid}&q=${encodeURIComponent(`Suggest replies to [m:${n.message.id}]`)}`}
                              className="text-cream-2 hover:bg-night-3 inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-sm font-semibold hover:text-cream"
                            >
                              <MessageSquareReply aria-hidden className="size-4" />
                              {n.replies.length ? "More replies" : "Draft replies"}
                            </Link>
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>

                {digest.decisions.length > 0 && (
                  <section aria-labelledby="decided">
                    <h2 id="decided" className="display text-[40px] text-cream sm:text-[52px]">
                      Decided while you were away
                    </h2>
                    <ul className="mt-5 grid gap-3">
                      {digest.decisions.map((d) => (
                        <li key={d.text} className="border-lime border-l-2 pl-5 text-[18px] leading-relaxed text-cream">
                          {d.text}
                          <Receipts ids={d.message_ids} onOpen={setOpen} />
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {digest.topics.length > 0 && (
                  <section aria-labelledby="missed">
                    <h2 id="missed" className="display text-[40px] text-cream sm:text-[52px]">
                      What everyone talked about
                    </h2>
                    <ol className="mt-5 grid gap-x-10 gap-y-7 md:grid-cols-2">
                      {digest.topics.map((t) => (
                        <li key={t.title}>
                          <h3 className="text-[20px] font-semibold text-cream">{t.title}</h3>
                          <p className="text-cream-2 mt-1 text-[16px] leading-relaxed">
                            {t.summary}
                            <Receipts ids={t.message_ids} onOpen={setOpen} />
                          </p>
                        </li>
                      ))}
                    </ol>
                  </section>
                )}

                {c.senders.length > 0 && (
                  <section aria-labelledby="who">
                    <h2 id="who" className="text-[20px] font-semibold text-cream">
                      Who was talking
                    </h2>
                    <ul className="mt-3 flex flex-wrap gap-2">
                      {c.senders.map((s) => (
                        <li key={s.participant_id} className="border-line-strong text-cream-2 rounded-full border px-4 py-1.5 text-[15px]">
                          <span className="text-cream">{s.name}</span> {formatCount(s.messages)}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                <div className="border-line flex flex-wrap items-center justify-between gap-4 border-t pt-8">
                  <p className="text-cream-2 text-[16px]">
                    Done reading? Next time, unread starts after {c.last_ts ? formatDay(c.last_ts) : "the last message"}.
                  </p>
                  <Button onClick={markAll} busy={marking}>
                    <Check aria-hidden className="size-4" /> Mark all as read
                  </Button>
                </div>
              </>
            ) : null}
          </div>
        )}
      </div>

      <AnimatePresence>
        {open !== null && (
          <>
            <motion.div className="bg-scrim fixed inset-0 z-40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(null)} />
            <motion.aside
              role="dialog"
              aria-label="Message in context"
              className="bg-night border-line fixed inset-y-0 right-0 z-50 w-[28rem] max-w-[92vw] overflow-y-auto border-l px-5 pb-8"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            >
              <button onClick={() => setOpen(null)} aria-label="Close" className="hover:bg-night-3 absolute top-4 right-3 z-20 grid size-10 place-items-center rounded-full">
                <X aria-hidden className="size-5" />
              </button>
              <Context key={open} pid={pid} id={open} meId={me?.id ?? null} onBack={() => setOpen(null)} backLabel="Back to catch up" />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
