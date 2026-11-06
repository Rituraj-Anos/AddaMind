"use client";

import {
  ArrowRight,
  ChevronDown,
  CircleCheck,
  FileArchive,
  Flame,
  LockKeyhole,
  MessageSquareQuote,
  MessagesSquare,
  ShieldCheck,
  Smartphone,
  Sparkles,
  TrendingUp,
  UserRoundCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { FillBar, Reveal, SmoothScroll } from "@/components/landing/motion";
import { Marquee } from "@/components/studio/Marquee";

// Every figure on this page is from the bundled demo chat (data/demo), and the page says the people are made up.

const NAV = [
  ["01", "Meet the agents", "#agents"],
  ["02", "How it works", "#how"],
  ["03", "Sample read", "#sample"],
  ["04", "Privacy", "#privacy"],
] as const;

function Cta({ children = "Read my chat", tone = "lime", big = false }: { children?: ReactNode; tone?: "lime" | "night"; big?: boolean }) {
  const t = tone === "lime" ? "on-lime bg-lime text-night shadow-pop hover:bg-lime-2" : "bg-night text-cream shadow-pop hover:bg-night-3";
  return (
    <Link
      href="/studio"
      className={`${t} inline-flex items-center gap-2 rounded-full font-semibold transition-[transform,box-shadow,background-color] duration-200 hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0.5 active:translate-y-0.5 ${
        big ? "h-14 px-8 text-[17px]" : "h-11 px-6 text-[15px]"
      }`}
    >
      {children} <ArrowRight aria-hidden className="size-4" />
    </Link>
  );
}

function Nav() {
  return (
    <header className="bg-night/95 border-line sticky top-0 z-40 border-b backdrop-blur-sm">
      <div className="mx-auto flex h-[72px] max-w-[80rem] items-center gap-8 px-6 lg:px-10">
        <Link href="/" className="display text-[30px] text-cream">
          AddaMind
        </Link>
        <nav aria-label="Sections" className="ml-6 hidden items-center gap-8 lg:flex">
          {NAV.map(([n, label, href]) => (
            <a key={href} href={href} className="text-cream-2 hover:text-cream group flex items-baseline gap-1.5 text-[15px] transition-colors">
              <span className="text-pink tabular font-mono text-[11px]">{n}</span>
              <span className="decoration-lime underline-offset-[10px] group-hover:underline">{label}</span>
            </a>
          ))}
        </nav>
        <div className="ml-auto">
          <Cta />
        </div>
      </div>
    </header>
  );
}

/** The hero's sample card, stacked on two tilted sheets like a printed read on a desk. */
function HeroCard() {
  return (
    <div className="relative mx-auto w-full max-w-[30rem] lg:mr-0">
      <div aria-hidden className="bg-pink absolute inset-0 translate-x-6 -translate-y-4 rotate-[5deg] rounded-[28px]" />
      <div aria-hidden className="bg-night-3 absolute inset-0 translate-x-3 -translate-y-2 rotate-[2.5deg] rounded-[28px]" />
      <article className="bg-paper text-ink shadow-lift relative rotate-[-1.5deg] rounded-[28px] p-6 transition-transform duration-500 hover:rotate-0 sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="display text-pink text-[15px] tracking-wide">AddaMind</p>
            <p className="text-[15px] font-semibold">Sample read</p>
          </div>
          <span className="border-pink text-pink rotate-[4deg] rounded-md border-2 px-2 py-1 font-mono text-[11px] font-bold">
            CITED
          </span>
        </div>
        <p className="text-ink-2 mt-6 font-mono text-[11px]">What the chat shows</p>
        <h2 className="display mt-2 text-[40px] leading-[0.95] sm:text-[46px]">Priya runs this group. Rohan narrates it.</h2>
        <p className="text-ink-2 mt-3 text-[16px] leading-snug">
          She starts a third of the conversations. He answers most of them in voice notes.
        </p>
        <dl className="border-rule mt-6 grid grid-cols-3 border-y">
          {[
            ["145", "chats started"],
            ["112", "voice notes"],
            ["157", "days of silence"],
          ].map(([v, l], i) => (
            <div key={l} className={`py-4 text-center ${i ? "border-rule border-l" : ""}`}>
              <dt className="display text-[32px] leading-none">{v}</dt>
              <dd className="text-ink-2 mt-1.5 font-mono text-[10px]">{l}</dd>
            </div>
          ))}
        </dl>
        <ul className="mt-5 grid gap-2 text-[14px]">
          <li className="bg-lime/40 flex items-start gap-2 rounded-xl px-3.5 py-2.5">
            <span className="bg-ink mt-1.5 size-1.5 shrink-0 rounded-full" />
            The mood dips in exam month and after the Darjeeling fight.
          </li>
          <li className="bg-paper-2 flex items-start gap-2 rounded-xl px-3.5 py-2.5">
            <span className="bg-pink mt-1.5 size-1.5 shrink-0 rounded-full" />
            &ldquo;3 baje Maggi&rdquo; started with Kabir, 16 March.
          </li>
        </ul>
        <p className="text-ink-2 mt-4 text-[12px]">Demo chat. Everyone in it is made up.</p>
      </article>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto grid max-w-[80rem] items-center gap-14 px-6 pt-10 pb-20 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:px-10 lg:pt-14 lg:pb-24">
        <div className="hero-in">
          <p className="border-line-strong inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-[13px] text-cream-2">
            <span className="bg-pink size-2 rounded-full" /> Private chat reader for WhatsApp groups and one-to-ones
          </p>
          <h1 className="display mt-6 text-[68px] text-cream sm:text-[96px] xl:text-[108px]">
            Read the adda.
            <span className="text-lime block">See the pattern.</span>
          </h1>
          <p className="text-cream-2 mt-6 max-w-[46ch] text-[19px] leading-relaxed">
            Upload a WhatsApp export. Four agents read every message and show you who carries the group, how the mood
            moved, and the receipts.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <Cta big />
            <a
              href="#sample"
              className="border-line-strong hover:border-cream inline-flex h-14 items-center rounded-full border px-7 text-[17px] font-semibold text-cream transition-colors"
            >
              See an example
            </a>
          </div>
          <p className="text-cream-3 mt-6 flex items-center gap-2 text-sm">
            <ShieldCheck aria-hidden className="text-pink size-4" /> Free to run, no sign-up, private by default
          </p>
        </div>
        <div className="hero-in hero-in-late">
          <HeroCard />
        </div>
      </div>
    </section>
  );
}

const RULES = [
  ["Bring receipts", "Every claim links to the message it came from. A citation the tools didn\u2019t return is removed before you see it."],
  ["Count, don\u2019t guess", "Who talks most, who starts things, who went quiet: exact counts from the chat, never a model\u2019s estimate."],
  ["Say when it can\u2019t tell", "If the chat doesn\u2019t show it, the answer says so. No filling gaps with general knowledge."],
];

const AGENTS = [
  ["Deep Analyzer", "Who drives the chat, how the mood moved, who replies to whom.", "bg-lime", "-rotate-3"],
  ["Roaster", "Playful roasts of habits, never identity. Tone from wholesome to savage.", "bg-pink", "rotate-2"],
  ["Memory Recall", "\u201cWhen did we\u2026\u201d and \u201cwho said\u2026\u201d, answered with the date.", "bg-ice", "-rotate-1"],
  ["Reply Giver", "Three to five replies in your own style, ready to copy.", "bg-cream", "rotate-3"],
] as const;

function Agents() {
  return (
    <section id="agents" className="bg-night-2 border-line relative overflow-hidden border-y">
      <div aria-hidden className="border-lime/15 pointer-events-none absolute -top-40 -right-40 size-[38rem] rounded-full border-[60px]" />
      <div className="relative mx-auto max-w-[80rem] px-6 py-20 lg:px-10 lg:py-28">
        <div className="border-line flex flex-wrap items-center justify-between gap-4 border-b pb-6">
          <p className="text-lime flex items-center gap-2 font-mono text-[12px]">
            <Sparkles aria-hidden className="size-4" /> Field file AM-04, your read&rsquo;s authors
          </p>
          <p className="border-line-strong text-cream-3 rounded-md border px-3 py-1.5 font-mono text-[11px]">
            Four agents, evidence first
          </p>
        </div>

        <div className="mt-14 grid items-center gap-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <Reveal>
            <ul className="relative mx-auto grid max-w-md gap-4">
              {AGENTS.map(([name, job, bg, tilt], i) => (
                <li
                  key={name}
                  className={`${bg} ${tilt} text-night rounded-[22px] p-5 shadow-[0_18px_40px_-18px_rgb(0_0_0_/_0.8)] transition-transform duration-300 hover:rotate-0 ${i % 2 ? "ml-10" : "mr-10"}`}
                >
                  <p className="display text-[30px] leading-none">{name}</p>
                  <p className="mt-2 text-[15px] leading-snug">{job}</p>
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={0.1}>
            <h2 className="display text-[64px] text-cream sm:text-[92px]">
              They don&rsquo;t read minds. They read messages.
            </h2>
            <p className="text-cream-2 mt-6 max-w-[52ch] text-[18px] leading-relaxed">
              Four agents share one memory of your chats. They search, count and quote before they say anything, and you
              can open every message they lean on.
            </p>
            <blockquote className="border-lime bg-night-3 mt-8 border-l-4 px-6 py-5 text-[22px] leading-snug text-cream">
              &ldquo;Counts come from the database. Claims come with receipts.&rdquo;
            </blockquote>
          </Reveal>
        </div>

        <div className="mt-24 flex items-center justify-between">
          <h3 className="display text-[44px] text-cream sm:text-[56px]">How an agent earns an answer</h3>
          <CircleCheck aria-hidden className="text-lime hidden size-9 sm:block" />
        </div>
        <ol className="border-line mt-8 grid border-t md:grid-cols-3">
          {RULES.map(([t, b], i) => (
            <li key={t} className={`border-line py-10 md:px-8 ${i ? "border-t md:border-t-0 md:border-l" : "md:pl-0"}`}>
              <Reveal delay={i * 0.08}>
                <span className="display text-cream/15 text-[88px] leading-none">0{i + 1}</span>
                <h4 className="mt-4 text-[22px] font-semibold text-cream">{t}</h4>
                <p className="text-cream-2 mt-3 text-[16px] leading-relaxed">{b}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const STEPS = [
  [FileArchive, "Add the chat", "Upload the WhatsApp export, with or without media. Voice notes and photos become searchable."],
  [UserRoundCheck, "Tell us who is who", "Pick which person is you, and switch off anyone who doesn\u2019t want to be roasted."],
  [MessageSquareQuote, "Ask the agents", "Get answers grounded in the whole chat, with the messages that prove them, one tap away."],
] as const;

const FORMATS = [
  ["Android export", "Open the chat, the three dots, More, Export chat, Include media. You get a .zip."],
  ["iPhone export", "Tap the chat name, Export chat, Attach media, Save to Files. Same .zip, read the same way."],
  ["Text only", "Exported without media? The .txt works. Add the .zip later and only the new parts are read."],
] as const;

function How() {
  return (
    <section id="how" className="bg-paper text-ink">
      <div className="mx-auto max-w-[80rem] px-6 py-20 lg:px-10 lg:py-28">
        <div className="grid items-end gap-8 lg:grid-cols-2">
          <Reveal>
            <h2 className="display text-[64px] sm:text-[92px]">From chat export to a clear read.</h2>
          </Reveal>
          <Reveal delay={0.1}>
            <p className="text-ink-2 max-w-[44ch] text-[20px] leading-relaxed">
              Add the chat, confirm the people, and get answers grounded in a year of conversation, not one dramatic
              message.
            </p>
          </Reveal>
        </div>
        <ol className="border-rule mt-14 grid border-y md:grid-cols-3">
          {STEPS.map(([Icon, t, b], i) => (
            <li key={t} className={`border-rule relative py-10 md:px-8 ${i ? "border-t md:border-t-0 md:border-l" : "md:pl-0"}`}>
              <Reveal delay={i * 0.08}>
                <div className="flex items-start justify-between">
                  <Icon aria-hidden className="text-pink size-7" strokeWidth={1.75} />
                  <span className="display text-ink/10 text-[64px] leading-none">0{i + 1}</span>
                </div>
                <h3 className="mt-6 text-[22px] font-semibold">{t}</h3>
                <p className="text-ink-2 mt-2 text-[16px] leading-relaxed">{b}</p>
              </Reveal>
            </li>
          ))}
        </ol>

        <div className="mt-28 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
          <Reveal>
            <h2 className="display text-[56px] sm:text-[80px]">Read the chat in the format you already have.</h2>
          </Reveal>
          <ul className="grid gap-px self-end overflow-hidden rounded-[24px] bg-rule sm:grid-cols-3">
            {FORMATS.map(([t, b], i) => (
              <li key={t} className="bg-paper p-6">
                <Reveal delay={i * 0.08}>
                  <div className="flex items-center justify-between">
                    <Smartphone aria-hidden className="text-pink size-6" strokeWidth={1.75} />
                    <span className="text-ink-2 font-mono text-[12px]">0{i + 1}</span>
                  </div>
                  <h3 className="display mt-6 text-[30px] leading-none">{t}</h3>
                  <p className="text-ink-2 mt-3 text-[15px] leading-relaxed">{b}</p>
                </Reveal>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function Bubble({ who, when, text, me = false }: { who: string; when: string; text: string; me?: boolean }) {
  return (
    <figure className={`max-w-[85%] ${me ? "ml-auto" : ""}`}>
      <blockquote className={`rounded-2xl px-4 py-3 text-[15px] leading-snug ${me ? "bg-lime rounded-br-md" : "bg-bubble rounded-bl-md"} text-ink`}>
        {text}
      </blockquote>
      <figcaption className={`text-ink-2 mt-1 text-[12px] ${me ? "text-right" : ""}`}>
        {who}, <time className="font-mono">{when}</time>
      </figcaption>
    </figure>
  );
}

function Split({ label, a, b, av, bv, note }: { label: string; a: string; b: string; av: number; bv: number; note: string }) {
  const share = av / (av + bv);
  return (
    <div className="py-6 sm:px-6">
      <p className="text-ink-2 font-mono text-[11px]">{label}</p>
      <div className="bg-pink mt-3 h-2.5 overflow-hidden rounded-full">
        <FillBar value={share} className="bg-ink rounded-full" />
      </div>
      <div className="mt-3 flex items-baseline justify-between text-[15px]">
        <span>
          {a} <b className="display ml-1 text-[24px]">{av}</b>
        </span>
        <span>
          {b} <b className="display ml-1 text-[24px]">{bv}</b>
        </span>
      </div>
      <p className="text-ink-2 mt-2 text-[14px]">{note}</p>
    </div>
  );
}

function Exhibit({ n, title, children, happened, read }: { n: string; title: string; children: ReactNode; happened: string; read: string }) {
  return (
    <Reveal>
      <article className="bg-bubble relative rounded-[24px] p-6 pt-8 shadow-[0_20px_50px_-30px_rgb(0_0_0_/_0.5)] sm:p-8 sm:pt-10">
        <span aria-hidden className="bg-lime/70 absolute -top-3 left-1/2 h-6 w-28 -translate-x-1/2 -rotate-2 rounded-sm" />
        <p className="font-mono text-[11px]">
          Exhibit {n} <span className="bg-ink ml-2 rounded px-1.5 py-0.5 text-cream">cited</span>
        </p>
        <h3 className="display mt-3 text-[36px] leading-none sm:text-[44px]">{title}</h3>
        <div className="bg-paper mt-6 flex flex-col gap-3 rounded-2xl p-4">{children}</div>
        <div className="border-rule mt-6 grid gap-6 border-t pt-6 sm:grid-cols-2">
          <div>
            <p className="text-ink-2 font-mono text-[11px]">What happened</p>
            <p className="mt-2 text-[15px] leading-relaxed">{happened}</p>
          </div>
          <div>
            <p className="text-pink font-mono text-[11px]">The read</p>
            <p className="mt-2 text-[15px] leading-relaxed">{read}</p>
          </div>
        </div>
      </article>
    </Reveal>
  );
}

function Sample() {
  return (
    <section id="sample" className="bg-paper-2 text-ink">
      <div className="mx-auto max-w-[68rem] px-4 py-20 sm:px-6 lg:py-28">
        <div className="bg-paper relative overflow-hidden rounded-[32px] px-6 py-12 sm:px-14 sm:py-16">
          {/* Ruled notebook paper with a margin line, drawn in the palette. */}
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_35px,var(--color-rule)_35px,var(--color-rule)_36px)] opacity-60" />
          <div aria-hidden className="bg-pink/60 pointer-events-none absolute inset-y-0 left-5 w-px sm:left-9" />
          <div className="relative">
            <p className="text-pink font-mono text-[12px]">Sample read / College Friends, the demo group</p>
            <h2 className="display mt-4 max-w-[16ch] text-[56px] leading-[0.92] sm:text-[84px]">
              Priya books the trips while Rohan books the airtime
            </h2>
            <p className="text-ink-2 mt-6 max-w-[60ch] text-[18px] leading-relaxed">
              Twenty friends, one year, 3,466 messages. One person keeps opening conversations; another answers almost
              everything out loud. The mood follows the college calendar.
            </p>
            <ul className="mt-6 flex flex-wrap gap-2 font-mono text-[11px]">
              {["20 people", "3,466 messages", "Feb 2025 to Jan 2026", "Group, understand"].map((t) => (
                <li key={t} className="border-rule bg-paper rounded-md border px-2.5 py-1.5">
                  {t}
                </li>
              ))}
            </ul>

            <Reveal>
              <div className="bg-night shadow-block relative mt-12 rounded-[24px] p-7 text-cream sm:p-10">
                <span className="border-lime text-lime absolute top-6 right-6 rotate-[6deg] rounded-md border-2 px-2.5 py-1 font-mono text-[12px] font-bold">
                  RULED
                </span>
                <p className="text-lime font-mono text-[12px]">The agents&rsquo; call, short version</p>
                <p className="mt-4 max-w-[30ch] text-[28px] leading-snug font-semibold sm:text-[36px]">
                  Priya is the engine: 16.5% of the messages and 145 of the 429 conversations started. The group is warmest on
                  trips and festivals and{" "}
                  <span className="decoration-lime underline decoration-[3px] underline-offset-[6px]">goes quiet in exam month</span>.
                </p>
                <div className="border-line mt-8 flex flex-wrap items-start gap-6 border-t pt-6">
                  <div>
                    <p className="text-cream-3 font-mono text-[11px]">Confidence</p>
                    <div className="mt-2 flex gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <span key={i} className="bg-lime h-2 w-7 rounded-full" />
                      ))}
                    </div>
                  </div>
                  <p className="text-cream-2 max-w-[56ch] flex-1 text-[16px] leading-relaxed">
                    <b className="text-cream">Next question:</b> ask who replies to Priya first, and who never does. The reply
                    graph has the answer, with the messages behind it.
                  </p>
                </div>
              </div>
            </Reveal>

            <div className="border-rule bg-paper mt-10 grid divide-y rounded-[20px] border sm:grid-cols-3 sm:divide-x sm:divide-y-0">
              <Split label="Conversations started" a="Priya" b="Next five" av={145} bv={162} note="Almost as many as the next five people together." />
              <Split label="Voice notes" a="Rohan" b="Everyone" av={112} bv={41} note="Three of every four voice notes are his." />
              <Split label="Messages after midnight" a="Kabir" b="Priya" av={82} bv={50} note="The night owl, by a distance." />
            </div>

            <div className="mt-14 grid gap-10">
              <Exhibit
                n="01"
                title="Abhishek forgot the tickets. Priya fixed it in a minute."
                happened="At 4:12 am on the day of the Goa flight, Abhishek says the printouts are at home. Priya answers sixty seconds later with the fix."
                read="The planner is also the one who cleans up. It's the same pattern as the conversation counts: Priya carries the group's logistics."
              >
                <Bubble who="Abhishek Kundu" when="14 Mar, 4:12" text="BHAI TICKETS GHAR PE BHOOL GAYA 😭😭 printout wala" />
                <Bubble who="Priya Sen" when="4:13" text="PNR se ho jayega, chill. Aadhaar hai na?" me />
              </Exhibit>
              <Exhibit
                n="02"
                title="Rohan's 'ek minute' is never a minute."
                happened="Rohan opens voice notes with 'ek minute' all year. By February the group is already teasing him for it."
                read="'Ek minute' is the chat's longest-running inside joke: 83 uses by 12 people, all traced back to Rohan's first voice note."
              >
                <Bubble who="Abhishek Kundu" when="20 Feb, 21:44" text="Rohan bhai tera 'ek minute' matlab 4 minute ka voice note 😭" />
                <Bubble who="Arjun Mehta" when="21:45" text="ek minute 💀💀" me />
              </Exhibit>
            </div>
            <p className="text-ink-2 mt-10 text-[13px]">Demo chat generated for AddaMind. Everyone in it is made up.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

const REVEALS = [
  [Users, "Who drives it", "See who starts conversations, who answers, and who the group waits for."],
  [TrendingUp, "The mood over time", "A month-by-month mood line, with the events behind each dip and high."],
  [Flame, "The inside jokes", "Every running joke, who started it, when, and how often it comes back."],
  [MessagesSquare, "What to say next", "Replies in your own style and language, Hinglish included, ready to copy."],
] as const;

function Reveals() {
  return (
    <section className="bg-night">
      <div className="mx-auto grid max-w-[80rem] items-center gap-14 px-6 py-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:px-10 lg:py-28">
        <Reveal>
          <p className="text-pink font-mono text-[12px]">A better way to read the room</p>
          <h2 className="display mt-5 text-[64px] text-cream sm:text-[88px]">What a group chat read can show.</h2>
          <p className="text-cream-2 mt-6 max-w-[46ch] text-[18px] leading-relaxed">
            One late reply means nothing. A year of them is a pattern. AddaMind reads the whole chat so you can see what
            stays consistent, what changed, and when.
          </p>
        </Reveal>
        <ul className="grid gap-4 sm:grid-cols-2">
          {REVEALS.map(([Icon, t, b], i) => (
            <li key={t}>
              <Reveal delay={i * 0.07} className="h-full">
                <div className="bg-night-2 border-line hover:border-line-strong h-full rounded-[22px] border p-6 transition-colors">
                  <div className="flex items-center justify-between">
                    <Icon aria-hidden className="text-pink size-6" strokeWidth={1.75} />
                    <span className="text-cream-3 font-mono text-[12px]">0{i + 1}</span>
                  </div>
                  <h3 className="mt-6 text-[20px] font-semibold text-cream">{t}</h3>
                  <p className="text-cream-2 mt-2 text-[15px] leading-relaxed">{b}</p>
                </div>
              </Reveal>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const INSIDE = [
  ["Big picture", "The overall vibe", "Who the group is, how it talks, and how that changed across the year.", false],
  ["Patterns", "Effort and habits", "Who reaches out, who replies fast, who sends voice notes at 3 am.", true],
  ["Next step", "What to do with it", "A roast, a reply, or the exact message where it all started.", false],
] as const;

function Inside() {
  return (
    <section className="bg-paper text-ink">
      <div className="mx-auto max-w-[80rem] px-6 py-20 lg:px-10 lg:py-28">
        <Reveal>
          <p className="text-pink font-mono text-[12px]">What&rsquo;s inside</p>
          <h2 className="display mt-4 text-[64px] sm:text-[92px]">What&rsquo;s inside every read.</h2>
        </Reveal>
        <ul className="mt-14 grid gap-8 md:grid-cols-3">
          {INSIDE.map(([k, t, b, hot], i) => (
            <li key={t}>
              <Reveal delay={i * 0.08} className="h-full">
                <div
                  className={`h-full rounded-[22px] p-7 transition-transform duration-300 hover:-translate-y-1 sm:p-8 ${
                    hot ? "bg-pink shadow-block text-ink" : "bg-bubble border-rule border"
                  }`}
                >
                  <div className="flex items-center justify-between font-mono text-[12px]">
                    <span className={hot ? "text-ink" : "text-ink-2"}>{k}</span>
                    <span>0{i + 1}</span>
                  </div>
                  <h3 className="display mt-14 text-[44px] leading-none">{t}</h3>
                  <p className={`mt-4 text-[16px] leading-relaxed ${hot ? "text-ink" : "text-ink-2"}`}>{b}</p>
                </div>
              </Reveal>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Privacy() {
  return (
    <section id="privacy" className="bg-paper-2 text-ink">
      <div className="mx-auto grid max-w-[80rem] items-center gap-14 px-6 py-20 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:px-10 lg:py-28">
        <Reveal>
          <div className="relative mx-auto grid aspect-square w-full max-w-[24rem] place-items-center">
            <div aria-hidden className="border-ink/20 absolute inset-0 rounded-full border" />
            <div aria-hidden className="border-pink absolute inset-[12%] animate-[spin_40s_linear_infinite] rounded-full border-2 border-dashed motion-reduce:animate-none" />
            <LockKeyhole aria-hidden className="text-pink size-20" strokeWidth={1.5} />
            <span className="bg-bubble border-ink absolute bottom-[10%] rotate-[-6deg] rounded-md border px-3 py-1.5 font-mono text-[12px] font-bold">
              PRIVATE BY DEFAULT
            </span>
          </div>
        </Reveal>
        <Reveal delay={0.1}>
          <p className="text-pink font-mono text-[12px]">Your chat is yours</p>
          <h2 className="display mt-4 text-[64px] sm:text-[88px]">Private chat reading, on your terms.</h2>
          <p className="text-ink-2 mt-6 max-w-[50ch] text-[18px] leading-relaxed">
            Your chats live in one project on this server. Projects never see each other. Delete a chat or a whole project
            and it&rsquo;s removed from disk. Photos and voice notes go to the AI services only to be described.
          </p>
          <ul className="border-rule mt-8 grid gap-4 border-t pt-6 sm:grid-cols-3">
            {["Private by default", "Delete any time", "Roast opt-outs"].map((t) => (
              <li key={t} className="flex items-center gap-2 text-[16px] font-semibold">
                <span className="bg-pink size-2 rounded-full" /> {t}
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  );
}

const FAQ = [
  [
    "What is AddaMind?",
    "A private reader for WhatsApp chats. You upload exports into a project, and four agents answer questions about them: patterns and mood, roasts, memories and replies. Every answer links to the messages it used.",
  ],
  [
    "Which chats can I upload?",
    "Any WhatsApp group or one-to-one chat, exported from Android or iPhone. A .zip with media is best; a .txt works too. Uploading a newer export of the same chat only adds what is new.",
  ],
  [
    "Does it make things up?",
    "It is built not to. Counts, rankings and dates come straight from the chat. Every citation is checked against what the agent actually found in that run, and anything it can\u2019t verify is removed. If the chat doesn\u2019t show something, the answer says so.",
  ],
  [
    "Who can see my chats?",
    "Only you, on the server you run it on. Photos, videos and voice notes are sent to the AI services only to be described or transcribed. Deleting a project removes it from disk.",
  ],
  [
    "Can it roast my friends without being mean?",
    "Roasts are about habits seen in the chat, like voice notes, late replies or catchphrases. They never touch looks, health, religion, caste, money or family, and a second check rewrites or drops anything unsafe. Anyone can be switched off from roasts.",
  ],
  [
    "Does it understand Hinglish?",
    "Yes. Messages are read as written, voice notes are transcribed with the group\u2019s own names and slang, and suggested replies keep the chat\u2019s language mix.",
  ],
] as const;

function Faq() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <section className="bg-night">
      <div className="mx-auto grid max-w-[80rem] gap-12 px-6 py-20 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:px-10 lg:py-28">
        <Reveal>
          <p className="text-pink font-mono text-[12px]">Questions before you start</p>
          <h2 className="display mt-5 text-[64px] text-cream sm:text-[80px]">What people ask about AddaMind.</h2>
        </Reveal>
        <ul className="border-line border-t">
          {FAQ.map(([q, a], i) => {
            const on = open === i;
            return (
              <li key={q} className="border-line border-b">
                <h3>
                  <button
                    aria-expanded={on}
                    aria-controls={`faq-${i}`}
                    onClick={() => setOpen(on ? null : i)}
                    className="flex w-full items-center justify-between gap-6 py-6 text-left text-[20px] font-semibold text-cream sm:text-[22px]"
                  >
                    {q}
                    <ChevronDown
                      aria-hidden
                      className={`text-pink size-5 shrink-0 transition-transform duration-300 ${on ? "rotate-180" : ""}`}
                    />
                  </button>
                </h3>
                <div
                  id={`faq-${i}`}
                  className={`grid transition-[grid-template-rows] duration-300 ease-out ${on ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
                >
                  <p className="text-cream-2 overflow-hidden pr-10 text-[17px] leading-relaxed">
                    <span className="block pb-6">{a}</span>
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="bg-paper text-ink border-ink border-t-[6px]">
      <div className="mx-auto max-w-[80rem] px-6 py-24 text-center lg:py-32">
        <Reveal>
          <h2 className="display mx-auto max-w-[14ch] text-[72px] sm:text-[120px]">Read the chat you keep scrolling back.</h2>
          <p className="text-ink-2 mx-auto mt-6 max-w-[44ch] text-[20px]">
            Start with one export. Keep it private, delete it whenever you like.
          </p>
          <div className="mt-10 flex justify-center">
            <Cta big tone="night" />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-night border-line border-t">
      <div className="mx-auto flex max-w-[80rem] flex-wrap items-end justify-between gap-6 px-6 py-12 lg:px-10">
        <div>
          <p className="display text-[44px] text-cream">AddaMind</p>
          <p className="text-cream-3 mt-1 text-sm">Every adda, remembered. Built for Agentic Chase, Mission 04.</p>
        </div>
        <nav aria-label="Footer" className="text-cream-2 flex flex-wrap gap-6 text-[15px]">
          <a href="#agents" className="hover:text-cream">Agents</a>
          <a href="#how" className="hover:text-cream">How it works</a>
          <a href="#sample" className="hover:text-cream">Sample read</a>
          <a href="#privacy" className="hover:text-cream">Privacy</a>
          <Link href="/studio" className="text-lime font-semibold">Open the studio</Link>
        </nav>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <>
      <SmoothScroll />
      <Nav />
      <main id="main">
        <Hero />
        <Marquee items={["Who drives it", "Mood swings", "Inside jokes", "Who replies to whom", "Roasts with receipts", "What to say next"]} seconds={40} />
        <Agents />
        <How />
        <Sample />
        <Reveals />
        <Inside />
        <Privacy />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
