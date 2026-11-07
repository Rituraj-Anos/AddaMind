"use client";

import { ArrowRight, FileArchive, LockKeyhole, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ExportHelp } from "@/components/studio/ExportHelp";
import { Marquee } from "@/components/studio/Marquee";
import { SampleRead } from "@/components/studio/SampleRead";
import { useStudio } from "@/components/studio/StudioProvider";
import { Avatar, Button, buttonClass, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { formatRange, plural } from "@/lib/format";
import type { Participant, Project, ProjectDetail } from "@/lib/types";

const THEMES = [
  "Who keeps the group going",
  "How the mood moved",
  "The inside jokes",
  "Who replies to whom",
  "A roast with receipts",
  "What to say next",
];

/** The hero's drop target: the whole block takes a drop, the button opens the picker. */
function StartDrop() {
  const { startWithFiles } = useStudio();
  const input = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<{ id: number; name: string } | null>(null);
  const [slow, setSlow] = useState(false);

  // If the page hasn't moved on a few seconds after the project was made, offer the way in by hand.
  useEffect(() => {
    if (!opened) return;
    const t = setTimeout(() => setSlow(true), 4000);
    return () => clearTimeout(t);
  }, [opened]);

  async function start(files: File[]) {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      const p = await startWithFiles(files);
      setOpened({ id: p.id, name: p.name });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1;
        if (depth.current <= 0) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        void start(Array.from(e.dataTransfer.files));
      }}
      className={`mt-9 rounded-[28px] border-2 border-dashed p-5 transition-colors duration-200 sm:p-6 ${
        over ? "border-lime bg-night-3" : "border-line-strong"
      }`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <button
          type="button"
          disabled={busy}
          onClick={() => input.current?.click()}
          className={buttonClass("primary", "md", "h-14 px-7 text-[17px]")}
        >
          {busy ? <Spinner className="size-5" /> : <FileArchive aria-hidden className="size-5" />}
          {busy ? "Starting" : "Choose the export"}
        </button>
        <p className="text-cream-2 text-[15px]">
          {over ? "Let go to start." : "or drop the .zip here. A .txt works too."}
        </p>
      </div>
      {error && (
        <p role="alert" className="text-alarm mt-3 text-sm">
          {error}
        </p>
      )}
      {slow && opened && (
        <p role="status" className="text-cream-2 mt-3 text-sm">
          Taking longer than it should.{" "}
          <a href={`/studio/${opened.id}`} className="text-lime font-semibold underline">
            Open {opened.name}
          </a>{" "}
          to see its progress.
        </p>
      )}
      <input
        ref={input}
        type="file"
        accept=".zip,.txt,application/zip,text/plain"
        multiple
        hidden
        onChange={(e) => {
          void start(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </div>
  );
}

/** Says where an upload goes. The public demo server keeps it to this browser and deletes it after a day. */
function PrivacyNote() {
  const [hours, setHours] = useState<number | null>(null);
  useEffect(() => {
    api
      .health()
      .then((h) => setHours(h.public ? (h.retention_hours ?? 24) : null))
      .catch(() => {});
  }, []);
  return (
    <p className="text-cream-3 mt-4 flex items-center gap-2 text-sm">
      <LockKeyhole aria-hidden className="size-4 shrink-0" />
      {hours === null
        ? "Kept on this server. Delete it and it\u2019s gone from disk."
        : `Only this browser can open it, and it\u2019s deleted from the server after ${plural(hours, "hour")}.`}
    </p>
  );
}

function Hero({ compact }: { compact: boolean }) {
  return (
    <section aria-labelledby="start-title" className="grid items-center gap-12 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <div className="min-w-0">
        <h1 id="start-title" className={`display text-cream ${compact ? "text-[56px] sm:text-[72px]" : "text-[64px] sm:text-[96px] xl:text-[112px]"}`}>
          {compact ? "Read another chat" : "Your group chat, finally read"}
        </h1>
        <p className="text-cream-2 mt-5 max-w-[44ch] text-[18px] sm:text-[20px]">
          Drop a WhatsApp export. Four agents read every message and point to the ones that matter.
        </p>
        <StartDrop />
        <PrivacyNote />
      </div>
      {!compact && <SampleRead />}
    </section>
  );
}

const STEPS = [
  {
    title: "Export the chat",
    body: "Any group or one-to-one chat. With media, voice notes become searchable too.",
  },
  {
    title: "Say which one is you",
    body: "So \u201cme\u201d in a question means you, and suggested replies sound like you.",
  },
  {
    title: "Ask, roast, recall",
    body: "Every answer links to the messages behind it. Tap one to read around it.",
  },
];

function HowItWorks() {
  return (
    <section aria-labelledby="how-title" className="border-line mt-24 border-t pt-14">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div>
          <h2 id="how-title" className="display text-[48px] text-cream sm:text-[56px]">
            From export to answers in three steps
          </h2>
          <div className="mt-8">
            <ExportHelp />
          </div>
        </div>
        <ol className="grid gap-8 sm:grid-cols-3 sm:gap-6">
          {STEPS.map((s, i) => (
            <li key={s.title} className="border-line sm:border-l sm:pl-6">
              <span className="display tabular text-lime text-[56px] leading-none">{i + 1}</span>
              <h3 className="mt-4 text-[18px] font-semibold text-cream">{s.title}</h3>
              <p className="text-cream-2 mt-2 text-[15px]">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/** One project as a tile: its name, its chats and the people in it. */
function ProjectTile({ p }: { p: Project }) {
  const { removeProject } = useStudio();
  const [detail, setDetail] = useState<{ project: ProjectDetail; people: Participant[] } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    let live = true;
    Promise.all([api.project(p.id), api.participants(p.id)])
      .then(([project, people]) => live && setDetail({ project, people }))
      .catch(() => {});
    return () => {
      live = false;
      clearTimeout(timer.current);
    };
  }, [p.id, p.chat_count]);

  const chats = detail?.project.chats ?? [];
  const people = detail?.people ?? [];
  const messages = chats.reduce((n, c) => n + c.message_count, 0);
  const first = chats.map((c) => c.first_ts).filter(Boolean).sort()[0] ?? null;
  const last = chats.map((c) => c.last_ts).filter(Boolean).sort().at(-1) ?? null;

  return (
    <li className="bg-night-2 border-line hover:border-line-strong group relative flex flex-col rounded-[28px] border p-6 transition-colors sm:p-7">
      <h3 className="display text-[44px] text-cream">
        <Link href={`/studio/${p.id}`} className="after:absolute after:inset-0 after:rounded-[28px]">
          {p.name}
        </Link>
      </h3>
      {detail ? (
        <>
          <p className="text-cream-2 mt-2 text-[15px]">
            {chats.length
              ? `${plural(chats.length, "chat")}, ${plural(people.length, "person", "people")}, ${plural(messages, "message")}`
              : "No chats yet"}
          </p>
          {chats.length > 0 && <p className="text-cream-3 text-sm">{formatRange(first, last)}</p>}
          {chats.length > 0 && (
            <ul className="mt-5 flex flex-wrap gap-2">
              {chats.slice(0, 4).map((c) => (
                <li key={c.id} className="border-line-strong rounded-full border px-3 py-1 text-sm text-cream">
                  {c.title}
                </li>
              ))}
            </ul>
          )}
          {people.length > 0 && (
            <div className="mt-6 flex items-center">
              {people.slice(0, 6).map((x, i) => (
                <span key={x.id} className={`ring-night-2 rounded-full ring-4 ${i ? "-ml-2" : ""}`}>
                  <Avatar name={x.name} id={x.id} me={x.is_me} size={34} />
                </span>
              ))}
              {people.length > 6 && <span className="text-cream-3 ml-3 text-sm">and {people.length - 6} more</span>}
            </div>
          )}
        </>
      ) : (
        <div className="mt-3 grid gap-2">
          <div className="skeleton h-4 w-56" />
          <div className="skeleton h-4 w-40" />
        </div>
      )}
      <div className="relative z-10 mt-auto flex items-center justify-between gap-3 pt-7">
        <span className="text-lime inline-flex items-center gap-1.5 text-[15px] font-semibold">
          Open <ArrowRight aria-hidden className="size-4 transition-transform duration-200 group-hover:translate-x-1" />
        </span>
        {confirming ? (
          <Button
            variant="danger"
            size="sm"
            busy={busy}
            onClick={async () => {
              setBusy(true);
              await removeProject(p.id).catch(() => setBusy(false));
            }}
          >
            Delete it all
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Delete ${p.name}`}
            className="size-9"
            onClick={() => {
              setConfirming(true);
              clearTimeout(timer.current);
              timer.current = setTimeout(() => setConfirming(false), 5000);
            }}
          >
            <Trash2 aria-hidden className="size-4" />
          </Button>
        )}
      </div>
    </li>
  );
}

export default function StartPage() {
  const { projects } = useStudio();
  const returning = projects.length > 0;
  return (
    <div className="pb-24">
      <Marquee items={THEMES} seconds={44} />
      <div className="mx-auto max-w-[76rem] px-6 pt-12 sm:pt-16 lg:px-12">
        {returning && (
          <section aria-labelledby="yours-title" className="mb-20">
            <h1 id="yours-title" className="display text-[64px] text-cream sm:text-[88px]">
              Your addas
            </h1>
            <ul className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((p) => (
                <ProjectTile key={p.id} p={p} />
              ))}
            </ul>
          </section>
        )}
        <Hero compact={returning} />
        {!returning && <HowItWorks />}
      </div>
    </div>
  );
}
