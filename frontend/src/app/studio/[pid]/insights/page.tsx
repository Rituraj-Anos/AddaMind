"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Context } from "@/components/ask/Evidence";
import { JokeDictionary } from "@/components/insights/JokeDictionary";
import { MoodTimeline } from "@/components/insights/MoodTimeline";
import { ReplyGraph } from "@/components/insights/ReplyGraph";
import { useStudio } from "@/components/studio/StudioProvider";
import { api, ApiError } from "@/lib/api";
import { formatRange } from "@/lib/format";
import type { ChatMemory, ReplyGraph as Graph } from "@/lib/types";

function Section({ id, title, lede, children }: { id: string; title: string; lede: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="border-line border-t pt-10">
      <h2 id={id} className="display text-[48px] text-cream sm:text-[64px]">
        {title}
      </h2>
      <p className="text-cream-2 mt-2 mb-8 max-w-[60ch] text-[17px]">{lede}</p>
      {children}
    </section>
  );
}

export default function InsightsPage() {
  const { project, pid, people } = useStudio();
  const search = useSearchParams();
  const router = useRouter();
  const chats = (project?.chats ?? []).filter((c) => c.status !== "failed");
  const cid = Number(search.get("chat")) || chats.sort((a, b) => b.message_count - a.message_count)[0]?.id || null;
  const chat = chats.find((c) => c.id === cid) ?? null;

  const [data, setData] = useState<{ cid: number; memory: ChatMemory | null; graph: Graph | null; error: string | null } | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    if (pid === null || cid === null) return;
    let live = true;
    Promise.allSettled([api.memory(pid, cid), api.graph(pid, cid)]).then(([m, g]) => {
      if (!live) return;
      const memErr = m.status === "rejected" ? (m.reason instanceof ApiError && m.reason.status === 404 ? null : String(m.reason?.message ?? m.reason)) : null;
      setData({
        cid,
        memory: m.status === "fulfilled" ? m.value : null,
        graph: g.status === "fulfilled" ? g.value : null,
        error: memErr ?? (g.status === "rejected" ? String(g.reason?.message ?? g.reason) : null),
      });
    });
    return () => {
      live = false;
    };
  }, [pid, cid, chat?.message_count, chat?.status]);

  if (!project || pid === null) return <div className="skeleton m-12 h-12 w-72 rounded-2xl" />;
  if (!chat)
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 lg:px-12">
        <h1 className="display text-[56px] text-cream">No chats to read yet</h1>
        <Link href={`/studio/${pid}`} className="text-lime mt-4 inline-block font-semibold underline">
          Add a chat
        </Link>
      </div>
    );

  const ready = data?.cid === cid ? data : null;
  const me = people.find((p) => p.is_me)?.id ?? null;

  return (
    <div className="pb-24">
      <div className="mx-auto max-w-[80rem] px-6 pt-12 lg:px-12 lg:pt-16">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h1 className="display text-[64px] text-cream sm:text-[96px]">{chat.title}</h1>
            <p className="text-cream-2 mt-2 text-[17px]">
              {chat.kind === "group" ? `Group of ${chat.member_count}` : "One to one"}, {formatRange(chat.first_ts, chat.last_ts)}
            </p>
          </div>
          {chats.length > 1 && (
            <div role="tablist" aria-label="Chat" className="flex flex-wrap gap-2">
              {chats.map((c) => (
                <button
                  key={c.id}
                  role="tab"
                  aria-selected={c.id === cid}
                  onClick={() => router.replace(`/studio/${pid}/insights?chat=${c.id}`, { scroll: false })}
                  className={`h-10 rounded-full px-5 text-[15px] font-semibold transition-colors ${
                    c.id === cid ? "bg-cream text-night" : "border-line-strong text-cream-2 hover:text-cream border"
                  }`}
                >
                  {c.title}
                </button>
              ))}
            </div>
          )}
        </div>

        {!ready ? (
          <div className="mt-14 grid gap-4">
            <div className="skeleton h-72 rounded-[28px]" />
            <div className="skeleton h-40 rounded-[28px]" />
          </div>
        ) : (
          <div className="mt-14 flex flex-col gap-20">
            {ready.error && (
              <p role="alert" className="text-alarm text-[15px]">
                Part of this page didn&rsquo;t load: {ready.error}
              </p>
            )}
            {ready.memory ? (
              <>
                <Section id="mood" title="The year in moods" lede="Each month scored from -1 (tense, sad) to +1 (happy), with the events behind it. Pick a month to read what happened.">
                  <MoodTimeline memory={ready.memory} onOpen={setOpen} />
                </Section>
                {ready.memory.dynamics && (
                  <Section id="dynamics" title="How this chat works" lede={ready.memory.dynamics.overview}>
                    <ul className="grid gap-x-10 gap-y-6 md:grid-cols-2">
                      {ready.memory.dynamics.patterns.map((p) => (
                        <li key={p} className="border-lime border-l-2 pl-5 text-[17px] leading-relaxed text-cream">
                          {p}
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}
              </>
            ) : (
              <p className="text-cream-2 border-line rounded-[24px] border p-6 text-[16px]">
                The memory for this chat isn&rsquo;t built yet, so the mood line and inside jokes will show once processing finishes.
                The reply graph below comes straight from the messages.
              </p>
            )}
            {ready.graph && (
              <Section id="graph" title="Who replies to whom" lede="A line means one person answered the other within ten minutes, or @mentioned them. Tap a person to see how they write.">
                <ReplyGraph pid={pid} cid={cid!} graph={ready.graph} />
              </Section>
            )}
            {ready.memory && (
              <Section id="jokes" title="Inside jokes" lede="Phrases the group keeps coming back to, each checked against the messages: who started it, when, and how often it returns.">
                <JokeDictionary jokes={ready.memory.inside_jokes} onOpen={setOpen} />
              </Section>
            )}
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
              <Context key={open} pid={pid} id={open} meId={me} onBack={() => setOpen(null)} backLabel="Back to insights" />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
