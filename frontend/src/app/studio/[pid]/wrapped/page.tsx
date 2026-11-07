"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { ArrowDown, Check, FileDown, Link2, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useStudio } from "@/components/studio/StudioProvider";
import { api } from "@/lib/api";
import { formatCount } from "@/lib/format";
import type { Award, ChatMemory, ChatStats } from "@/lib/types";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const first = (n: string) => (n.startsWith("+") ? n : n.split(" ")[0]);
const day = (d: string) => new Date(d + "T00:00").toLocaleString("en-GB", { weekday: "long", day: "numeric", month: "long" });
const month = (m: string) => new Date(m + "-01T00:00").toLocaleString("en-GB", { month: "long" });

/** A number that counts up from zero when its slide arrives (data-count is read by the GSAP setup). */
function Count({ value, decimals = 0, suffix = "" }: { value: number; decimals?: number; suffix?: string }) {
  return (
    <span className="tabular" data-count={value} data-decimals={decimals} data-suffix={suffix}>
      {value.toLocaleString("en-IN", { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}
      {suffix}
    </span>
  );
}

function Slide({ tone, children, label }: { tone: string; children: React.ReactNode; label: string }) {
  return (
    <section aria-label={label} className={`slide ${tone} relative flex min-h-dvh items-center overflow-hidden`}>
      <div className="mx-auto w-full max-w-[80rem] px-6 py-24 sm:px-12">{children}</div>
    </section>
  );
}

const AWARD_LINE: Record<Award["award"], (a: Award) => string> = {
  night_owl: (a) => `${formatCount(a.value)} messages between midnight and 4 am.`,
  ghost: (a) => `Went silent for ${formatCount(Math.round(a.value))} days at a stretch.`,
  speed_replier: (a) => `Half their replies land within ${Math.round(a.value / 60) || 1} minute${Math.round(a.value / 60) > 1 ? "s" : ""}.`,
  essayist: (a) => `${formatCount(Math.round(a.value))} characters a message, on average.`,
  hype_machine: (a) => `${formatCount(a.value)} emoji. Nobody else comes close.`,
  lurker: (a) => `${formatCount(a.value)} messages all year. Reading everything, saying little.`,
};
const AWARD_TONE = ["bg-cream", "bg-lime", "bg-pink", "bg-ice", "bg-cream", "bg-lime"];
const TILT = ["-rotate-2", "rotate-2", "-rotate-1", "rotate-1", "-rotate-2", "rotate-2"];

function MoodBars({ memory }: { memory: ChatMemory }) {
  return (
    <ul className="mt-12 flex h-[38vh] items-center gap-[1.2%]">
      {memory.mood.map((m) => {
        const h = Math.max(6, Math.abs(m.mood) * 100);
        return (
          <li key={m.month} className="flex h-full flex-1 flex-col items-center">
            <div className="flex w-full flex-1 items-end">
              {m.mood > 0 && <span className="mood-bar bg-night block w-full rounded-t-xl" style={{ height: `${h}%` }} />}
            </div>
            <span className="bg-night/30 my-1 h-0.5 w-full" />
            <div className="flex w-full flex-1 items-start">
              {m.mood <= 0 && <span className="mood-bar bg-pink block w-full rounded-b-xl" style={{ height: `${h}%` }} />}
            </div>
            <span className="mt-2 text-[12px] font-semibold sm:text-[14px]">{month(m.month).slice(0, 3)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function ShareButton() {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(window.location.href).catch(() => {});
        setDone(true);
        setTimeout(() => setDone(false), 2500);
      }}
      className="bg-night text-cream hover:bg-night-3 inline-flex h-14 items-center gap-2 rounded-full px-8 text-[17px] font-semibold transition-colors"
    >
      {done ? <Check aria-hidden className="size-5" /> : <Link2 aria-hidden className="size-5" />}
      {done ? "Link copied" : "Copy the link"}
    </button>
  );
}

export default function WrappedPage() {
  const { project, pid } = useStudio();
  const search = useSearchParams();
  const chats = [...(project?.chats ?? [])].filter((c) => c.status !== "failed").sort((a, b) => b.message_count - a.message_count);
  const chat = chats.find((c) => c.id === Number(search.get("chat"))) ?? chats.find((c) => c.kind === "group") ?? chats[0] ?? null;
  const [data, setData] = useState<{ cid: number; stats: ChatStats; memory: ChatMemory | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

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

  const ready = data && chat && data.cid === chat.id ? data : null;

  // Lenis drives the scroll; ScrollTrigger reads it. Nothing moves under reduced motion.
  useEffect(() => {
    if (!ready || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (t: number) => lenis.raf(t * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
    };
  }, [ready]);

  useGSAP(
    () => {
      if (!ready) return;
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.utils.toArray<HTMLElement>(".slide").forEach((slide) => {
          const lines = slide.querySelectorAll(".line");
          gsap.from(lines, {
            yPercent: 60,
            opacity: 0,
            duration: 0.9,
            ease: "expo.out",
            stagger: 0.08,
            scrollTrigger: { trigger: slide, start: "top 70%" },
          });
          slide.querySelectorAll<HTMLElement>("[data-count]").forEach((el) => {
            const v = Number(el.dataset.count), d = Number(el.dataset.decimals), s = el.dataset.suffix ?? "";
            const o = { n: 0 };
            gsap.to(o, {
              n: v,
              duration: 1.6,
              ease: "power3.out",
              scrollTrigger: { trigger: slide, start: "top 65%" },
              onUpdate: () => {
                el.textContent = o.n.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }) + s;
              },
            });
          });
          gsap.from(slide.querySelectorAll(".mood-bar"), {
            scaleY: 0,
            transformOrigin: (i: number, el: HTMLElement) => (el.classList.contains("bg-pink") ? "top" : "bottom"),
            duration: 0.8,
            ease: "expo.out",
            stagger: 0.05,
            scrollTrigger: { trigger: slide, start: "top 60%" },
          });
          gsap.from(slide.querySelectorAll(".card"), {
            y: 120,
            rotate: 0,
            opacity: 0,
            duration: 1,
            ease: "expo.out",
            stagger: 0.09,
            scrollTrigger: { trigger: slide, start: "top 65%" },
          });
          // The giant word on each slide drifts against the scroll.
          gsap.to(slide.querySelectorAll(".drift"), {
            xPercent: -18,
            ease: "none",
            scrollTrigger: { trigger: slide, start: "top bottom", end: "bottom top", scrub: true },
          });
        });
      });
      return () => mm.revert();
    },
    { scope: root, dependencies: [ready] },
  );

  const back = pid !== null ? `/studio/${pid}` : "/studio";
  const close = (
    <Link
      href={back}
      aria-label="Close Wrapped"
      className="bg-night/80 text-cream hover:bg-night fixed top-4 right-4 z-50 grid size-12 place-items-center rounded-full backdrop-blur-sm"
    >
      <X aria-hidden className="size-5" />
    </Link>
  );

  if (error || (project && !chat))
    return (
      <div className="bg-night grid min-h-dvh place-items-center px-6 text-center">
        {close}
        <div>
          <h1 className="display text-[56px] text-cream">No Wrapped yet</h1>
          <p className="text-cream-2 mt-3">{error ?? "Upload a chat first."}</p>
        </div>
      </div>
    );

  if (!ready || !chat)
    return (
      <div className="bg-lime text-night grid min-h-dvh place-items-center">
        {close}
        <p className="display animate-pulse text-[64px] motion-reduce:animate-none">Wrapping it up</p>
      </div>
    );

  const { stats, memory } = ready;
  const h = stats.highlights;
  const top = stats.participants[0];
  const busiest = stats.activity.busiest_day;
  const joke = memory?.inside_jokes[0];
  const couple = h.power_couple;
  const high = memory?.mood.reduce((a, b) => (b.mood > a.mood ? b : a), memory.mood[0]);
  const low = memory?.mood.reduce((a, b) => (b.mood < a.mood ? b : a), memory.mood[0]);
  const years = [stats.totals.first?.slice(0, 4), stats.totals.last?.slice(0, 4)].filter(Boolean);
  const span = years[0] === years[1] ? years[0] : years.join(" to ");

  return (
    <div ref={root} className="bg-night">
      {close}

      <Slide tone="bg-lime text-night" label="Cover">
        <p className="line text-[20px] font-semibold">{chat.title}</p>
        <h1 className="line display mt-4 text-[22vw] leading-[0.82] sm:text-[17vw]">Wrapped</h1>
        <p className="line mt-6 max-w-[34ch] text-[22px] leading-snug sm:text-[28px]">
          {span}, {formatCount(stats.totals.participants)} people, <Count value={stats.totals.messages} /> messages. Here&rsquo;s what they
          added up to.
        </p>
        <p className="line mt-14 flex items-center gap-2 text-[16px] font-semibold">
          <ArrowDown aria-hidden className="size-5 animate-bounce motion-reduce:animate-none" /> Scroll
        </p>
      </Slide>

      {top && (
        <Slide tone="bg-night text-cream" label="Top talker">
          <p className="drift display text-cream/5 pointer-events-none absolute top-1/2 left-0 -translate-y-1/2 text-[34vw] leading-none whitespace-nowrap">
            {first(top.name)} {first(top.name)}
          </p>
          <div className="relative">
            <p className="line text-lime text-[20px] font-semibold">The loudest voice</p>
            <h2 className="line display mt-4 text-[16vw] leading-[0.85] sm:text-[11vw]">{top.name}</h2>
            <p className="line mt-8 text-[24px] sm:text-[32px]">
              <span className="display text-lime text-[64px] sm:text-[96px]">
                <Count value={top.messages} />
              </span>{" "}
              messages, <Count value={top.share * 100} decimals={1} suffix="%" /> of everything said.
            </p>
          </div>
        </Slide>
      )}

      {h.conversation_starter && (
        <Slide tone="bg-pink text-night" label="Conversation starter">
          <p className="line text-[20px] font-semibold">Who says hi first</p>
          <h2 className="line display mt-4 text-[14vw] leading-[0.85] sm:text-[10vw]">{h.conversation_starter.name}</h2>
          <p className="line mt-8 max-w-[30ch] text-[26px] leading-snug sm:text-[34px]">
            Started <b className="display text-[56px] sm:text-[80px]"><Count value={h.conversation_starter.starts} /></b> of the{" "}
            {formatCount(stats.totals.conversations)} conversations. Without them, the group goes quiet.
          </p>
        </Slide>
      )}

      {busiest && (
        <Slide tone="bg-cream text-night" label="Busiest day">
          <p className="line text-[20px] font-semibold">The busiest day</p>
          <h2 className="line display mt-4 text-[12vw] leading-[0.85] sm:text-[8vw]">{day(busiest.date)}</h2>
          <p className="line mt-8 text-[26px] sm:text-[34px]">
            <b className="display text-[64px] sm:text-[96px]"><Count value={busiest.messages} /></b> messages in one day.
          </p>
          {memory?.timeline.find((e) => e.date === busiest.date) && (
            <p className="line mt-4 max-w-[48ch] text-[20px] leading-snug text-night/75">
              {memory.timeline.find((e) => e.date === busiest.date)!.detail}
            </p>
          )}
        </Slide>
      )}

      {h.voice_note_king && (
        <Slide tone="bg-ice text-night" label="Voice-note king">
          <p className="line text-[20px] font-semibold">Too busy to type</p>
          <h2 className="line display mt-4 text-[14vw] leading-[0.85] sm:text-[10vw]">{h.voice_note_king.name}</h2>
          <p className="line mt-8 max-w-[32ch] text-[26px] leading-snug sm:text-[34px]">
            <b className="display text-[64px] sm:text-[96px]"><Count value={h.voice_note_king.voice_notes} /></b> voice notes, out of{" "}
            {formatCount(stats.totals.media.voice ?? 0)} in the whole chat.
          </p>
        </Slide>
      )}

      {memory && memory.mood.length > 1 && high && low && (
        <Slide tone="bg-lime text-night" label="The year in moods">
          <p className="line text-[20px] font-semibold">The year in moods</p>
          <h2 className="line display mt-4 max-w-[16ch] text-[10vw] leading-[0.88] sm:text-[6.5vw]">
            Best in {month(high.month)}. Toughest in {month(low.month)}.
          </h2>
          <MoodBars memory={memory} />
          <p className="line mt-6 max-w-[60ch] text-[18px] leading-snug">{low.reason}</p>
        </Slide>
      )}

      {joke && (
        <Slide tone="bg-night text-cream" label="The biggest inside joke">
          <p className="line text-pink text-[20px] font-semibold">The joke that never died</p>
          <h2 className="line display text-pink mt-4 text-[16vw] leading-[0.85] sm:text-[11vw]">&ldquo;{joke.phrase}&rdquo;</h2>
          <p className="line mt-8 max-w-[40ch] text-[24px] leading-snug sm:text-[30px]">
            Said <b className="display text-[56px] sm:text-[80px]"><Count value={joke.uses} /></b> times by {joke.people} people. It started with{" "}
            {joke.started_by} on {new Date(joke.first_date + "T00:00").toLocaleString("en-GB", { day: "numeric", month: "long" })}.
          </p>
          <p className="line text-cream-2 mt-4 max-w-[52ch] text-[18px]">{joke.meaning}</p>
        </Slide>
      )}

      {couple && (
        <Slide tone="bg-pink text-night" label="The closest pair">
          <p className="line text-[20px] font-semibold">Always replying to each other</p>
          <h2 className="line display mt-4 text-[12vw] leading-[0.88] sm:text-[8vw]">
            {first(couple.names[0])} <span className="opacity-50">and</span> {first(couple.names[1])}
          </h2>
          <p className="line mt-8 text-[26px] sm:text-[34px]">
            <b className="display text-[64px] sm:text-[96px]"><Count value={couple.interactions} /></b> quick replies and mentions between them.
          </p>
        </Slide>
      )}

      {stats.awards.length > 0 && (
        <Slide tone="bg-night text-cream" label="Awards">
          <p className="line text-lime text-[20px] font-semibold">And the awards go to</p>
          <h2 className="line display mt-4 text-[12vw] leading-[0.85] sm:text-[7vw]">The class of {span}</h2>
          <ul className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {stats.awards.map((a, i) => (
              <li key={a.award} className={`card ${AWARD_TONE[i]} ${TILT[i]} text-night rounded-[28px] p-6 sm:p-7`}>
                <p className="display text-[40px] leading-none">{a.title}</p>
                <p className="mt-5 text-[22px] font-semibold">{a.name}</p>
                <p className="mt-1 text-[16px] leading-snug">{AWARD_LINE[a.award](a)}</p>
              </li>
            ))}
          </ul>
        </Slide>
      )}

      <Slide tone="bg-cream text-night" label="The end">
        <h2 className="line display text-[18vw] leading-[0.82] sm:text-[13vw]">That was {span}.</h2>
        <p className="line mt-6 max-w-[40ch] text-[22px] leading-snug">
          Every number here was counted from the chat itself. Ask the agents for the stories behind them.
        </p>
        <div className="line mt-10 flex flex-wrap gap-4">
          <ShareButton />
          <Link
            href={`/studio/${pid}/report?chat=${chat.id}`}
            className="border-night hover:bg-night hover:text-cream inline-flex h-14 items-center gap-2 rounded-full border-2 px-8 text-[17px] font-semibold transition-colors"
          >
            <FileDown aria-hidden className="size-5" /> Export as PDF
          </Link>
          <Link
            href={`/studio/${pid}/ask?chat=${chat.id}`}
            className="border-night hover:bg-night hover:text-cream inline-flex h-14 items-center rounded-full border-2 px-8 text-[17px] font-semibold transition-colors"
          >
            Ask about {chat.title}
          </Link>
        </div>
        {chats.length > 1 && (
          <p className="line mt-10 text-[16px]">
            Also wrapped:{" "}
            {chats
              .filter((c) => c.id !== chat.id)
              .map((c, i) => (
                <span key={c.id}>
                  {i > 0 && ", "}
                  <Link href={`/studio/${pid}/wrapped?chat=${c.id}`} className="font-semibold underline">
                    {c.title}
                  </Link>
                </span>
              ))}
          </p>
        )}
      </Slide>
    </div>
  );
}
