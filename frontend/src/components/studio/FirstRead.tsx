"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatCount, formatRange, percent, plural } from "@/lib/format";
import type { Award, Chat, ChatStats } from "@/lib/types";
import { Avatar } from "../ui";

const first = (name: string) => (name.startsWith("+") ? name : name.split(" ")[0]);

function duration(s: number): string {
  if (s < 90) return `${Math.round(s)} seconds`;
  if (s < 5400) return `${Math.round(s / 60)} minutes`;
  return `${Math.round(s / 3600)} hours`;
}

/** One sentence that says who carries the chat, from the exact counts. */
function lead(s: ChatStats, kind: Chat["kind"]): string {
  const top = s.participants[0];
  const starter = s.highlights.conversation_starter;
  const total = s.totals.conversations;
  if (!top) return "No messages from people yet.";
  if (kind === "direct" && s.participants.length >= 2) {
    const [a, b] = s.participants;
    const st = starter ? `${first(starter.name)} opens ${formatCount(starter.starts)} of the ${formatCount(total)} conversations.` : "";
    return `${first(a.name)} sends ${percent(a.share)} of the messages, ${first(b.name)} ${percent(b.share)}. ${st}`;
  }
  if (starter && starter.participant_id === top.id)
    return `${first(top.name)} sends ${percent(top.share)} of the messages and starts ${formatCount(starter.starts)} of the ${formatCount(total)} conversations.`;
  return `${first(top.name)} talks the most (${percent(top.share)} of the messages)${
    starter ? `, but ${first(starter.name)} starts more conversations: ${formatCount(starter.starts)} of ${formatCount(total)}` : ""
  }.`;
}

function headline(s: ChatStats, kind: Chat["kind"]): string {
  const starter = s.highlights.conversation_starter;
  const top = s.participants[0];
  if (kind === "direct") return s.participants.length >= 2 ? `${first(s.participants[0].name)} and ${first(s.participants[1].name)}` : "One to one";
  const who = starter ?? (top && { name: top.name });
  return who ? `${first(who.name)} keeps this group going` : "A quiet group";
}

function awardLine(a: Award): string {
  switch (a.award) {
    case "night_owl":
      return `${plural(a.value, "message")} between midnight and 4 am`;
    case "ghost":
      return `Silent for ${formatCount(Math.round(a.value))} days at a stretch`;
    case "speed_replier":
      return `Half their replies come within ${duration(a.value)}`;
    case "essayist":
      return `${formatCount(Math.round(a.value))} characters a message, on average`;
    case "hype_machine":
      return `${plural(a.value, "emoji", "emoji")} sent`;
    case "lurker":
      return `Only ${plural(a.value, "message")} all year`;
  }
}

const AWARD_TONES = ["bg-cream", "bg-lime", "bg-pink", "bg-ice"] as const;
const TILTS = ["-rotate-2", "rotate-1", "-rotate-1", "rotate-2"] as const;

function ShareBars({ s }: { s: ChatStats }) {
  const people = s.participants.slice(0, 5);
  const max = people[0]?.share || 1;
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(t);
  }, []);
  return (
    <figure>
      <figcaption className="text-cream-3 text-sm">Share of messages</figcaption>
      <ul className="mt-3 grid gap-3">
        {people.map((p, i) => (
          <li key={p.id} className="grid grid-cols-[7.5rem_minmax(0,1fr)_3.5rem] items-center gap-3 sm:grid-cols-[9rem_minmax(0,1fr)_4rem]">
            <span className="truncate text-[15px] text-cream">{first(p.name)}</span>
            <span className="bg-night-3 h-3 overflow-hidden rounded-full">
              <span
                className={`block h-full origin-left rounded-full transition-transform duration-700 ease-out motion-reduce:transition-none ${
                  i === 0 ? "bg-lime" : "bg-cream-2"
                }`}
                style={{ transform: `scaleX(${shown ? p.share / max : 0})`, transitionDelay: `${i * 60}ms` }}
              />
            </span>
            <span className="tabular text-right text-[15px] text-cream">{percent(p.share)}</span>
          </li>
        ))}
      </ul>
      {s.participants.length > 5 && (
        <p className="text-cream-3 mt-3 text-sm">
          {plural(s.participants.length - 5, "other person", "other people")} share the remaining{" "}
          {percent(1 - s.participants.slice(0, 5).reduce((n, p) => n + p.share, 0))}.
        </p>
      )}
    </figure>
  );
}

function AwardCard({ a, i }: { a: Award; i: number }) {
  return (
    <li
      className={`${AWARD_TONES[i % 4]} ${TILTS[i % 4]} w-[15.5rem] shrink-0 snap-start rounded-[24px] p-5 text-night transition-transform duration-200 hover:rotate-0 motion-reduce:transition-none`}
    >
      <p className="display text-[30px] leading-none">{a.title}</p>
      <p className="mt-4 flex items-center gap-2 text-[16px] font-semibold">
        <Avatar name={a.name} id={a.participant_id} size={28} />
        {a.name}
      </p>
      <p className="mt-2 text-[14px] leading-snug">{awardLine(a)}</p>
    </li>
  );
}

const AGENTS = [
  { key: "analyzer", name: "Deep Analyzer", text: "text-lime" },
  { key: "roaster", name: "Roaster", text: "text-pink" },
  { key: "recall", name: "Memory Recall", text: "text-ice" },
  { key: "reply", name: "Reply Giver", text: "text-cream-2" },
] as const;

function questions(s: ChatStats, chat: Chat): Record<(typeof AGENTS)[number]["key"], string> {
  const voice = s.highlights.voice_note_king;
  const owl = s.awards.find((a) => a.award === "night_owl");
  const target = voice ? `${first(voice.name)} about the voice notes` : owl ? `${first(owl.name)} for the late nights` : `${first(s.participants[0]?.name ?? "them")}`;
  return {
    analyzer:
      chat.kind === "group"
        ? `Who drives ${chat.title}, and how did the mood change over the year?`
        : `How has my chat with ${chat.title} changed over time?`,
    roaster: `Roast ${target}`,
    recall: chat.kind === "group" ? "What trips did we plan, and who backed out?" : `What did ${chat.title} and I last plan?`,
    reply: `What should I reply to ${chat.kind === "group" ? "the group" : chat.title}'s last message?`,
  };
}

export function FirstRead({ pid, chat }: { pid: number; chat: Chat }) {
  const [stats, setStats] = useState<ChatStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .chatStats(pid, chat.id)
      .then((s) => live && setStats(s))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [pid, chat.id, chat.message_count]);

  const heading = (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
      <h2 className="display text-[44px] text-cream sm:text-[56px]">{chat.title}</h2>
      <p className="text-cream-3 text-sm">
        {chat.kind === "group" ? `Group of ${chat.member_count}` : "One to one"}, {formatRange(chat.first_ts, chat.last_ts)},{" "}
        {plural(chat.message_count, "message")}
      </p>
    </div>
  );

  if (error)
    return (
      <section className="border-line border-t pt-10">
        {heading}
        <p role="alert" className="text-alarm mt-4 text-sm">
          The first read didn&rsquo;t load: {error}
        </p>
      </section>
    );

  if (!stats)
    return (
      <section aria-busy className="border-line border-t pt-10">
        {heading}
        <div className="skeleton mt-6 h-10 w-[min(36rem,100%)] rounded-2xl" />
        <div className="mt-8 grid gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-3" />
          ))}
        </div>
      </section>
    );

  const q = questions(stats, chat);
  return (
    <section aria-label={`First read of ${chat.title}`} className="border-line border-t pt-10">
      {heading}

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] lg:gap-14">
        <div>
          <p className="display text-[40px] text-lime sm:text-[52px]">{headline(stats, chat.kind)}</p>
          <p className="text-cream-2 mt-4 max-w-[52ch] text-[17px]">{lead(stats, chat.kind)}</p>
        </div>
        <ShareBars s={stats} />
      </div>

      {stats.awards.length > 0 && (
        <div className="mt-12">
          <h3 className="text-[17px] font-semibold text-cream">Awards, decided by the numbers</h3>
          <ul className="-mx-6 mt-5 flex snap-x gap-4 overflow-x-auto px-6 pt-2 pb-5 lg:-mx-2 lg:px-2">
            {stats.awards.map((a, i) => (
              <AwardCard key={a.award} a={a} i={i} />
            ))}
          </ul>
        </div>
      )}

      <div className="mt-10">
        <h3 className="text-[17px] font-semibold text-cream">Ask about {chat.title}</h3>
        <ul className="border-line mt-3 border-t">
          {AGENTS.map((a) => (
            <li key={a.key} className="border-line border-b">
              <Link
                href={`/studio/${pid}/ask?chat=${chat.id}&agent=${a.key}&q=${encodeURIComponent(q[a.key])}`}
                className="group grid items-baseline gap-1 py-4 sm:grid-cols-[11rem_minmax(0,1fr)_auto] sm:gap-6"
              >
                <span className={`text-[15px] font-semibold ${a.text}`}>{a.name}</span>
                <span className="text-[19px] leading-snug text-cream group-hover:underline group-hover:decoration-line-strong">
                  {q[a.key]}
                </span>
                <ArrowUpRight
                  aria-hidden
                  className="text-cream-3 hidden size-5 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-cream sm:block"
                />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
