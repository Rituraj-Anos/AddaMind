"use client";

import { ArrowLeft, FileDown } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useStudio } from "@/components/studio/StudioProvider";
import { api } from "@/lib/api";
import { formatCount, formatDay, formatRange, percent, plural } from "@/lib/format";
import type { ChatMemory, ChatStats } from "@/lib/types";

const first = (n: string) => (n.startsWith("+") ? n : n.split(" ")[0]);
const monthName = (m: string) => new Date(m + "-01T00:00").toLocaleString("en-GB", { month: "short", year: "2-digit" });
const reply = (s: number | null) => (s === null ? "n/a" : s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

function Block({ title, kicker, children }: { title: string; kicker: string; children: ReactNode }) {
  return (
    <section className="border-rule mt-14 break-inside-avoid border-t pt-8">
      <p className="text-pink font-mono text-[11px]">{kicker}</p>
      <h2 className="display mt-2 text-[40px] leading-none sm:text-[52px]">{title}</h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function Stat({ label, name, value, note }: { label: string; name: string; value: string; note: string }) {
  return (
    <div className="py-5 break-inside-avoid sm:px-5">
      <p className="text-ink-2 font-mono text-[11px]">{label}</p>
      <p className="mt-2 text-[20px] font-semibold">{name}</p>
      <p className="display mt-1 text-[36px]">{value}</p>
      <p className="text-ink-2 mt-1 text-[14px]">{note}</p>
    </div>
  );
}

/** A printable read of one chat, in the landing page's sample style. Every number comes from the stats endpoint (SQL). */
export default function ReportPage() {
  const { project, pid } = useStudio();
  const search = useSearchParams();
  const router = useRouter();
  const chats = [...(project?.chats ?? [])].filter((c) => c.status !== "failed").sort((a, b) => b.message_count - a.message_count);
  const chat = chats.find((c) => c.id === Number(search.get("chat"))) ?? chats.find((c) => c.kind === "group") ?? chats[0] ?? null;
  const [data, setData] = useState<{ cid: number; stats: ChatStats; memory: ChatMemory | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (pid === null || !chat) return;
    let live = true;
    Promise.all([api.chatStats(pid, chat.id), api.memory(pid, chat.id).catch(() => null)])
      .then(([stats, memory]) => live && setData({ cid: chat.id, stats, memory }))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [pid, chat]);

  // The browser uses the page title as the PDF file name.
  useEffect(() => {
    if (!chat) return;
    const prev = document.title;
    document.title = `${chat.title} - AddaMind read`;
    return () => {
      document.title = prev;
    };
  }, [chat]);

  const back = pid !== null ? `/studio/${pid}/insights${chat ? `?chat=${chat.id}` : ""}` : "/studio";
  const ready = data && chat && data.cid === chat.id ? data : null;

  if (error || (project && !chat))
    return (
      <div className="bg-paper text-ink grid min-h-dvh place-items-center px-6 text-center">
        <div>
          <h1 className="display text-[56px]">No report yet</h1>
          <p className="text-ink-2 mt-3">{error ?? "Upload a chat first."}</p>
          <Link href={back} className="mt-6 inline-block font-semibold underline">
            Back
          </Link>
        </div>
      </div>
    );

  if (!ready || !chat)
    return (
      <div className="bg-paper text-ink grid min-h-dvh place-items-center">
        <p role="status" className="display animate-pulse text-[56px] motion-reduce:animate-none">
          Writing the report
        </p>
      </div>
    );

  const { stats, memory } = ready;
  const h = stats.highlights;
  const top = stats.participants[0];
  const night = [...stats.participants].sort((a, b) => b.night_messages - a.night_messages)[0];
  const mood = memory?.mood ?? [];
  const high = mood.length ? mood.reduce((a, b) => (b.mood > a.mood ? b : a)) : null;
  const low = mood.length ? mood.reduce((a, b) => (b.mood < a.mood ? b : a)) : null;
  const headline =
    h.conversation_starter && top && h.conversation_starter.participant_id !== top.id
      ? `${first(h.conversation_starter.name)} starts the conversations, ${first(top.name)} does the talking`
      : top
        ? `${first(top.name)} carries ${chat.title}`
        : chat.title;

  return (
    <div className="report bg-paper-2 text-ink min-h-dvh">
      <div className="bg-paper-2/90 sticky top-0 z-30 backdrop-blur-sm print:hidden">
        <div className="mx-auto flex max-w-[60rem] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link href={back} className="hover:bg-paper inline-flex h-10 items-center gap-2 rounded-full px-4 text-[15px] font-semibold">
            <ArrowLeft aria-hidden className="size-4" /> Back
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            {chats.length > 1 && (
              <label className="text-ink-2 flex items-center gap-2 text-[14px]">
                Chat
                <select
                  value={chat.id}
                  onChange={(e) => router.replace(`/studio/${pid}/report?chat=${e.target.value}`, { scroll: false })}
                  className="border-rule bg-paper text-ink h-10 rounded-full border px-3 text-[15px]"
                >
                  {chats.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              onClick={() => window.print()}
              className="bg-ink text-cream hover:bg-night-3 inline-flex h-10 items-center gap-2 rounded-full px-5 text-[15px] font-semibold transition-colors"
            >
              <FileDown aria-hidden className="size-4" /> Save as PDF
            </button>
          </div>
        </div>
        <p className="text-ink-2 mx-auto max-w-[60rem] px-4 pb-3 text-[13px] sm:px-6">
          In the print window, choose &ldquo;Save as PDF&rdquo;, then send the file to the group.
        </p>
      </div>

      <main className="mx-auto max-w-[60rem] px-4 pb-20 sm:px-6 print:max-w-none print:p-0">
        <article className="bg-paper relative overflow-hidden rounded-[32px] px-6 py-12 sm:px-14 sm:py-16 print:rounded-none print:px-0 print:py-0">
          <p className="text-pink font-mono text-[12px]">AddaMind read / {chat.title}</p>
          <h1 className="display mt-4 max-w-[18ch] text-[52px] leading-[0.92] sm:text-[76px]">{headline}</h1>
          {memory?.dynamics?.overview && <p className="text-ink-2 mt-6 max-w-[62ch] text-[18px] leading-relaxed">{memory.dynamics.overview}</p>}
          <ul className="mt-6 flex flex-wrap gap-2 font-mono text-[11px]">
            {[
              plural(stats.totals.participants, "person", "people"),
              plural(stats.totals.messages, "message"),
              plural(stats.totals.conversations, "conversation"),
              formatRange(stats.totals.first, stats.totals.last),
              chat.kind === "group" ? "Group" : "One to one",
            ].map((t) => (
              <li key={t} className="border-rule bg-paper rounded-md border px-2.5 py-1.5">
                {t}
              </li>
            ))}
          </ul>

          <div className="border-rule divide-rule mt-10 grid divide-y rounded-[20px] border break-inside-avoid sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4 print:grid-cols-4 print:divide-x print:divide-y-0">
            {top && <Stat label="Most messages" name={top.name} value={percent(top.share)} note={`${plural(top.messages, "message")} of ${formatCount(stats.totals.messages)}`} />}
            {h.conversation_starter && (
              <Stat label="Starts conversations" name={h.conversation_starter.name} value={formatCount(h.conversation_starter.starts)} note={`of ${formatCount(stats.totals.conversations)} conversations`} />
            )}
            {h.voice_note_king && (
              <Stat label="Voice notes" name={h.voice_note_king.name} value={formatCount(h.voice_note_king.voice_notes)} note={`of ${formatCount(stats.totals.media.voice ?? 0)} in the chat`} />
            )}
            {night && night.night_messages > 0 && <Stat label="After midnight" name={night.name} value={formatCount(night.night_messages)} note="messages between midnight and 4 am" />}
          </div>

          <Block kicker="Counted from every message" title="Who talks">
            <table className="w-full text-left text-[14px]">
              <thead className="text-ink-2 font-mono text-[11px]">
                <tr>
                  <th className="py-2 font-normal">Person</th>
                  <th className="w-[34%] py-2 font-normal">Share</th>
                  <th className="py-2 text-right font-normal">Messages</th>
                  <th className="hidden py-2 text-right font-normal sm:table-cell print:table-cell">Started</th>
                  <th className="hidden py-2 text-right font-normal sm:table-cell print:table-cell">Typical reply</th>
                </tr>
              </thead>
              <tbody>
                {stats.participants.slice(0, 12).map((p) => (
                  <tr key={p.id} className="border-rule border-t break-inside-avoid">
                    <td className="py-2 pr-3 font-semibold">{p.name}</td>
                    <td className="py-2 pr-3">
                      <span className="bg-paper-2 block h-2 overflow-hidden rounded-full">
                        <span className="bg-ink block h-full rounded-full" style={{ width: `${Math.max(2, (p.share / (top?.share || 1)) * 100)}%` }} />
                      </span>
                    </td>
                    <td className="tabular py-2 text-right">{formatCount(p.messages)}</td>
                    <td className="tabular hidden py-2 text-right sm:table-cell print:table-cell">{formatCount(p.conversation_starts)}</td>
                    <td className="tabular hidden py-2 text-right sm:table-cell print:table-cell">{reply(p.median_reply_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {stats.participants.length > 12 && <p className="text-ink-2 mt-3 text-[13px]">And {plural(stats.participants.length - 12, "more person", "more people")}.</p>}
          </Block>

          {stats.awards.length > 0 && (
            <Block kicker="Each one a rule over the counts" title="The awards">
              <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 print:grid-cols-3">
                {stats.awards.map((a) => (
                  <li key={a.award} className="bg-bubble rounded-[20px] p-5 break-inside-avoid">
                    <p className="display text-[28px] leading-none">{a.title}</p>
                    <p className="mt-3 text-[17px] font-semibold">{a.name}</p>
                    <p className="text-ink-2 mt-1 text-[14px] leading-snug">{a.rule}</p>
                  </li>
                ))}
              </ul>
            </Block>
          )}

          {mood.length > 1 && high && low && (
            <Block kicker="Monthly mood, -1 to +1" title={`Best in ${monthName(high.month)}, toughest in ${monthName(low.month)}`}>
              <ul className="flex h-40 items-center gap-1" aria-label="Mood by month">
                {mood.map((m) => {
                  const hgt = `${Math.max(6, Math.abs(m.mood) * 100)}%`;
                  return (
                    <li key={m.month} className="flex h-full flex-1 flex-col items-center" title={`${monthName(m.month)}: ${m.mood.toFixed(2)}`}>
                      <div className="flex w-full flex-1 items-end">{m.mood > 0 && <span className="bg-ink block w-full rounded-t-md" style={{ height: hgt }} />}</div>
                      <span className="bg-rule h-px w-full" />
                      <div className="flex w-full flex-1 items-start">{m.mood <= 0 && <span className="bg-pink block w-full rounded-b-md" style={{ height: hgt }} />}</div>
                      <span className="text-ink-2 mt-1 font-mono text-[9px]">{monthName(m.month).slice(0, 3)}</span>
                    </li>
                  );
                })}
              </ul>
              <div className="mt-6 grid gap-6 sm:grid-cols-2 print:grid-cols-2">
                <div>
                  <p className="text-ink-2 font-mono text-[11px]">The high, {monthName(high.month)}</p>
                  <p className="mt-2 text-[15px] leading-relaxed">{high.reason}</p>
                </div>
                <div>
                  <p className="text-pink font-mono text-[11px]">The low, {monthName(low.month)}</p>
                  <p className="mt-2 text-[15px] leading-relaxed">{low.reason}</p>
                </div>
              </div>
            </Block>
          )}

          {memory && memory.timeline.length > 0 && (
            <Block kicker="From the chat's memory" title="Moments">
              <ol className="grid gap-4">
                {memory.timeline.slice(0, 10).map((e) => (
                  <li key={e.date + e.title} className="grid gap-1 break-inside-avoid sm:grid-cols-[9rem_1fr] sm:gap-4 print:grid-cols-[9rem_1fr] print:gap-4">
                    <time className="text-ink-2 font-mono text-[12px]">{formatDay(e.date + " 00:00")}</time>
                    <div>
                      <p className="text-[16px] font-semibold">{e.title}</p>
                      <p className="text-ink-2 text-[14px] leading-relaxed">{e.detail}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </Block>
          )}

          {memory && memory.inside_jokes.length > 0 && (
            <Block kicker="Each one checked against the messages" title="Inside jokes">
              <ul className="grid gap-4 sm:grid-cols-2 print:grid-cols-2">
                {memory.inside_jokes.slice(0, 6).map((j) => (
                  <li key={j.phrase} className="bg-bubble rounded-[20px] p-5 break-inside-avoid">
                    <p className="display text-[30px] leading-none">&ldquo;{j.phrase}&rdquo;</p>
                    <p className="mt-3 text-[14px] leading-relaxed">{j.meaning}</p>
                    <p className="text-ink-2 mt-2 font-mono text-[11px]">
                      {plural(j.uses, "use")} by {plural(j.people, "person", "people")}, started by {j.started_by}, {formatDay(j.first_date + " 00:00")}
                    </p>
                  </li>
                ))}
              </ul>
            </Block>
          )}

          {memory?.dynamics && (memory.dynamics.patterns.length > 0 || memory.dynamics.roles.length > 0) && (
            <Block kicker="The agents' read" title="How this chat works">
              <ul className="grid gap-3">
                {memory.dynamics.patterns.map((p) => (
                  <li key={p} className="border-pink border-l-2 pl-4 text-[15px] leading-relaxed break-inside-avoid">
                    {p}
                  </li>
                ))}
              </ul>
              {memory.dynamics.roles.length > 0 && (
                <dl className="mt-6 grid gap-x-8 gap-y-3 sm:grid-cols-2 print:grid-cols-2">
                  {memory.dynamics.roles.map((r) => (
                    <div key={r.name} className="break-inside-avoid">
                      <dt className="text-[15px] font-semibold">{r.name}</dt>
                      <dd className="text-ink-2 text-[14px]">{r.role}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </Block>
          )}

          <p className="text-ink-2 border-rule mt-14 border-t pt-6 text-[12px]">
            Counted from {plural(stats.totals.messages, "message")} by AddaMind on{" "}
            {new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}. Counts come from the chat itself; the
            mood, moments and patterns are the agents&rsquo; read of it.
          </p>
        </article>
      </main>
    </div>
  );
}
