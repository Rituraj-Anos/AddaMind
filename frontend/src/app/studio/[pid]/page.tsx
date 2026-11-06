"use client";

import { ArrowRight, Check, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { FirstRead } from "@/components/studio/FirstRead";
import { JobTrack, liveLines, StagePreview, UploadRow } from "@/components/studio/JobTrack";
import { Marquee } from "@/components/studio/Marquee";
import { useStudio } from "@/components/studio/StudioProvider";
import { UploadZone } from "@/components/studio/UploadZone";
import { Avatar, Button, Chip, Spinner } from "@/components/ui";
import { formatCount, formatRange, plural } from "@/lib/format";
import type { Chat, Participant } from "@/lib/types";

const PEOPLE_SHOWN = 10;

function useTwoStep(ms = 5000) {
  const [armed, setArmed] = useState(false);
  const t = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(t.current), []);
  return {
    armed,
    arm: () => {
      setArmed(true);
      clearTimeout(t.current);
      t.current = setTimeout(() => setArmed(false), ms);
    },
  };
}

function ChatRow({ c, pid }: { c: Chat; pid: number }) {
  const { removeChat } = useStudio();
  const del = useTwoStep();
  const [busy, setBusy] = useState(false);
  return (
    <tr className="border-line border-b last:border-b-0">
      <th scope="row" className="py-4 pr-4 text-left align-top font-normal">
        <span className="block text-[17px] font-semibold text-cream">{c.title}</span>
        <span className="text-cream-3 text-sm">{formatRange(c.first_ts, c.last_ts)}</span>
      </th>
      <td className="text-cream-2 hidden py-4 pr-4 align-top text-[15px] md:table-cell">
        {c.kind === "group" ? "Group" : "One to one"}
      </td>
      <td className="tabular hidden py-4 pr-4 text-right align-top text-[15px] text-cream sm:table-cell">
        {formatCount(c.message_count)}
      </td>
      <td className="tabular hidden py-4 pr-4 text-right align-top text-[15px] text-cream md:table-cell">
        {formatCount(c.member_count)}
      </td>
      <td className="tabular hidden py-4 pr-4 text-right align-top text-[15px] text-cream lg:table-cell">
        {formatCount(c.media_count)}
      </td>
      <td className="py-3 align-top">
        <div className="flex items-center justify-end gap-2">
          {c.status === "processing" ? (
            <span className="text-lime inline-flex h-8 items-center gap-2 text-sm">
              <Spinner /> Processing
            </span>
          ) : c.status === "failed" ? (
            <Chip tone="alarm">Failed</Chip>
          ) : (
            <Link
              href={`/studio/${pid}/ask?chat=${c.id}`}
              className="border-line-strong hover:border-cream hover:bg-night-3 inline-flex h-8 items-center gap-1.5 rounded-full border px-3.5 text-sm font-semibold text-cream transition-colors"
            >
              Ask about it <ArrowRight aria-hidden className="size-3.5" />
            </Link>
          )}
          {del.armed ? (
            <Button
              variant="danger"
              size="sm"
              busy={busy}
              onClick={async () => {
                setBusy(true);
                await removeChat(c.id).catch(() => setBusy(false));
              }}
            >
              Delete for good
            </Button>
          ) : (
            <Button variant="ghost" size="icon" aria-label={`Delete ${c.title}`} onClick={del.arm} className="size-8">
              <Trash2 aria-hidden className="size-4" />
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}

/** Quiet when on (the default); opting out is the state worth noticing, so off is pink. */
function Switch({ on, label, onChange }: { on: boolean; label: string; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors duration-200 ${
        on ? "border-line-strong bg-night-3" : "border-pink bg-pink"
      }`}
    >
      <span
        className={`size-[18px] rounded-full transition-transform duration-200 ${
          on ? "bg-cream translate-x-[21px]" : "bg-night translate-x-[2px]"
        }`}
      />
    </button>
  );
}

function PersonRow({ p }: { p: Participant }) {
  const { setMe, setRoastOptOut } = useStudio();
  const [err, setErr] = useState<string | null>(null);
  const run = (f: () => Promise<void>) => () => {
    setErr(null);
    f().catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  };
  return (
    <tr className="border-line group hover:bg-night-2 border-b transition-colors last:border-b-0">
      <th scope="row" className="py-3 pr-4 text-left font-normal">
        <span className="flex items-center gap-3">
          <Avatar name={p.name} id={p.id} me={p.is_me} />
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-[15px] font-semibold text-cream">{p.name}</span>
              {p.is_me && <Chip tone="lime">You</Chip>}
            </span>
            {err && <span className="text-alarm block text-sm">{err}</span>}
          </span>
        </span>
      </th>
      <td className="tabular py-3 pr-4 text-right text-[15px] text-cream">{formatCount(p.message_count)}</td>
      <td className="tabular hidden py-3 pr-4 text-right text-[15px] text-cream sm:table-cell">{p.chat_ids.length}</td>
      <td className="py-3 pr-4">
        <span className="flex items-center gap-3">
          <Switch
            on={!p.roast_opt_out}
            label={`${p.name} can be roasted`}
            onChange={(v) => run(() => setRoastOptOut(p.id, !v))()}
          />
          <span className={`hidden text-sm lg:inline ${p.roast_opt_out ? "text-pink font-semibold" : "text-cream-3"}`}>
            {p.roast_opt_out ? "Opted out" : "Fair game"}
          </span>
        </span>
      </td>
      <td className="py-3 text-right">
        {!p.is_me && (
          // Shown on row hover or keyboard focus with a mouse; always shown on touch screens.
          <button
            onClick={run(() => setMe(p.id))}
            className="text-cream-2 hover:text-cream focus-visible:opacity-100 text-sm font-semibold whitespace-nowrap underline decoration-line-strong transition-opacity duration-150 hover:decoration-cream [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 [@media(hover:hover)]:group-focus-within:opacity-100"
          >
            This is me
          </button>
        )}
      </td>
    </tr>
  );
}

function WhoIsMe({ people }: { people: Participant[] }) {
  const { setMe } = useStudio();
  const [busy, setBusy] = useState<number | null>(null);
  const top = people.filter((p) => !p.masked).slice(0, 8);
  return (
    <section aria-labelledby="me-title" className="bg-cream text-night rounded-3xl p-6 sm:p-8">
      <h2 id="me-title" className="display text-[36px]">
        Which one is you?
      </h2>
      <p className="mt-2 max-w-[60ch] text-[15px]">
        The agents read the chats from your side: &ldquo;me&rdquo; in a question means you, and replies are written in
        your style.
      </p>
      <ul className="mt-5 flex flex-wrap gap-2">
        {top.map((p) => (
          <li key={p.id}>
            <button
              onClick={async () => {
                setBusy(p.id);
                await setMe(p.id).finally(() => setBusy(null));
              }}
              className="border-night hover:bg-night inline-flex h-10 items-center gap-2 rounded-full border-2 pr-4 pl-1 text-[15px] font-semibold transition-colors hover:text-cream"
            >
              {busy === p.id ? <Spinner className="mx-2 size-4" /> : <Avatar name={p.name} id={p.id} size={30} tone />}
              {p.name}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Heading({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h2 className="display flex items-baseline gap-4 text-[40px] text-cream">
      {children}
      {count !== undefined && <span className="text-cream-3 font-sans text-lg font-semibold normal-case">{formatCount(count)}</span>}
    </h2>
  );
}

/** The project name, renamed in place: click it, type, Enter saves, Escape cancels. */
function EditableName({ name }: { name: string }) {
  const { renameProject } = useStudio();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const clean = value.trim();
    if (!clean || clean === name) {
      setEditing(false);
      setValue(name);
      return;
    }
    setBusy(true);
    try {
      await renameProject(clean);
      setEditing(false);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!editing)
    return (
      <h1 className="display text-[56px] text-cream sm:text-[88px]">
        <button
          onClick={() => {
            setValue(name);
            setEditing(true);
          }}
          className="group inline-flex max-w-full items-center gap-4 text-left uppercase"
          aria-label={`${name}. Rename`}
        >
          <span className="min-w-0 break-words">{name}</span>
          <Pencil aria-hidden className="text-cream-3 size-6 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
        </button>
      </h1>
    );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      className="flex flex-wrap items-center gap-3"
    >
      <label htmlFor="rename" className="sr-only">
        Project name
      </label>
      <input
        id="rename"
        autoFocus
        value={value}
        maxLength={80}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && (setEditing(false), setValue(name))}
        className="display border-lime bg-night-2 h-[72px] min-w-0 flex-1 rounded-2xl border-2 px-4 text-[48px] text-cream outline-none sm:h-[96px] sm:text-[72px]"
      />
      <Button type="submit" busy={busy}>
        Save name
      </Button>
      <Button type="button" variant="ghost" onClick={() => (setEditing(false), setValue(name))}>
        Cancel
      </Button>
      {error && <p className="text-alarm w-full text-sm">{error}</p>}
    </form>
  );
}

/** Where a new project stands: add a chat, say who you are, then ask. */
function Setup({ chats, me, ready }: { chats: boolean; me: boolean; ready: boolean }) {
  const steps = [
    { label: "Add a chat", done: chats },
    { label: "Say which one is you", done: me },
    { label: "Ask the agents", done: false, live: ready && me },
  ];
  const current = steps.findIndex((s) => !s.done);
  return (
    <ol aria-label="Setting up" className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-2">
      {steps.map((s, i) => (
        <li key={s.label} className="flex items-center gap-3">
          <span
            aria-current={i === current ? "step" : undefined}
            className={`inline-flex h-9 items-center gap-2 rounded-full px-4 text-[15px] font-semibold ${
              s.done ? "bg-night-3 text-cream-2" : i === current ? "on-lime bg-lime text-night" : "border-line-strong text-cream-3 border"
            }`}
          >
            {s.done ? <Check aria-hidden className="size-4" strokeWidth={3} /> : <span className="tabular">{i + 1}</span>}
            {s.label}
            <span className="sr-only">{s.done ? ", done" : i === current ? ", current step" : ""}</span>
          </span>
          {i < steps.length - 1 && <span aria-hidden className="bg-line-strong h-px w-6" />}
        </li>
      ))}
    </ol>
  );
}

/** One chat's first read at a time; tabs switch between chats (arrow keys move between tabs). */
function Reads({ pid, chats }: { pid: number; chats: Chat[] }) {
  const sorted = [...chats].sort((a, b) => b.message_count - a.message_count);
  const [picked, setPicked] = useState<number | null>(null);
  const current = sorted.find((c) => c.id === picked) ?? sorted[0];
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  return (
    <div className="mt-14">
      {sorted.length > 1 && (
        <div
          role="tablist"
          aria-label="Chats"
          className="mb-2 flex gap-2 overflow-x-auto pb-2"
          onKeyDown={(e) => {
            if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
            const i = sorted.findIndex((c) => c.id === current.id);
            const next = (i + (e.key === "ArrowRight" ? 1 : -1) + sorted.length) % sorted.length;
            setPicked(sorted[next].id);
            tabs.current[next]?.focus();
          }}
        >
          {sorted.map((c, i) => {
            const on = c.id === current.id;
            return (
              <button
                key={c.id}
                ref={(el) => {
                  tabs.current[i] = el;
                }}
                role="tab"
                id={`tab-${c.id}`}
                aria-selected={on}
                aria-controls="read-panel"
                tabIndex={on ? 0 : -1}
                onClick={() => setPicked(c.id)}
                className={`inline-flex h-10 shrink-0 items-center gap-2 rounded-full px-5 text-[15px] font-semibold transition-colors ${
                  on ? "bg-cream text-night" : "border-line-strong text-cream-2 hover:text-cream border"
                }`}
              >
                {c.title}
                <span className={`tabular text-sm font-normal ${on ? "text-night/60" : "text-cream-3"}`}>
                  {formatCount(c.message_count)}
                </span>
              </button>
            );
          })}
        </div>
      )}
      <div id="read-panel" role={sorted.length > 1 ? "tabpanel" : undefined} aria-labelledby={sorted.length > 1 ? `tab-${current.id}` : undefined}>
        <FirstRead key={current.id} pid={pid} chat={current} />
      </div>
    </div>
  );
}

function SkeletonRows({ n = 3 }: { n?: number }) {
  return (
    <div role="status" aria-label="Loading" className="mt-6 grid gap-3">
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skeleton h-14 rounded-2xl" />
      ))}
    </div>
  );
}

export default function ProjectPage() {
  const { project, pid, people, jobs, uploads, missing, dismissUpload } = useStudio();
  const [allPeople, setAllPeople] = useState(false);

  const shown = jobs;
  const lines = liveLines(jobs);

  if (missing)
    return (
      <div className="mx-auto max-w-6xl px-6 py-16 lg:px-12">
        <h1 className="display text-[56px] text-cream">No such project</h1>
        <p className="text-cream-2 mt-3">It may have been deleted.</p>
        <Link href="/studio" className="text-lime mt-6 inline-block font-semibold underline">
          See all projects
        </Link>
      </div>
    );

  if (!project || pid === null)
    return (
      <div className="mx-auto max-w-6xl px-6 py-14 lg:px-12">
        <div className="skeleton h-16 w-80 rounded-2xl" />
        <SkeletonRows />
      </div>
    );

  const messages = project.chats.reduce((n, c) => n + c.message_count, 0);
  const hasMe = people.some((p) => p.is_me);
  const ready = project.chats.filter((c) => c.status === "ready");
  const working = uploads.length > 0 || shown.some((j) => j.status === "running" || j.status === "queued");
  const empty = project.chats.length === 0 && !working && shown.length === 0;

  return (
    <div className="pb-24">
      {lines.length > 0 && <Marquee items={lines} />}
      <div className="mx-auto max-w-[76rem] px-6 pt-12 lg:px-12 lg:pt-16">
        <EditableName name={project.name} />
        <p className="text-cream-2 mt-3 text-[17px]">
          {empty
            ? "No chats yet. Add the first export below."
            : `${plural(project.chats.length, "chat")}, ${plural(people.length, "person", "people")}, ${plural(messages, "message")}.`}
        </p>

        {(!hasMe || ready.length === 0) && (
          <Setup chats={project.chats.length > 0 || working} me={hasMe} ready={ready.length > 0} />
        )}

        {(empty || working || shown.length > 0) && (
          <div className="mt-10 flex flex-col gap-4">
            {empty && <UploadZone />}
            {uploads.map((u) => (
              <UploadRow key={u.id} u={u} onDismiss={() => dismissUpload(u.id)} />
            ))}
            {shown.map((j) => (
              <JobTrack key={j.id} job={j} />
            ))}
          </div>
        )}

        {empty && (
          <div className="mt-14">
            <StagePreview />
          </div>
        )}

        {people.length > 0 && !hasMe && (
          <div className="mt-10">
            <WhoIsMe people={people} />
          </div>
        )}

        {ready.length > 0 && <Reads pid={pid} chats={ready} />}

        {!empty && (
          <div className="mt-20">
            <UploadZone compact />
          </div>
        )}

        {project.chats.length > 0 && (
          <section aria-labelledby="chats-title" className="mt-20">
            <Heading count={project.chats.length}>
              <span id="chats-title">Chats</span>
            </Heading>
            <table className="mt-4 w-full border-collapse">
              <thead>
                <tr className="border-line text-cream-3 border-b text-left text-sm">
                  <th scope="col" className="pb-2 font-semibold">Chat</th>
                  <th scope="col" className="hidden pb-2 font-semibold md:table-cell">Kind</th>
                  <th scope="col" className="hidden pb-2 pr-4 text-right font-semibold sm:table-cell">Messages</th>
                  <th scope="col" className="hidden pb-2 pr-4 text-right font-semibold md:table-cell">People</th>
                  <th scope="col" className="hidden pb-2 pr-4 text-right font-semibold lg:table-cell">Media</th>
                  <th scope="col" className="pb-2"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {project.chats.map((c) => (
                  <ChatRow key={c.id} c={c} pid={pid} />
                ))}
              </tbody>
            </table>
          </section>
        )}

        {people.length > 0 && (
          <section aria-labelledby="people-title" className="mt-16">
            <Heading count={people.length}>
              <span id="people-title">People</span>
            </Heading>
            <p className="text-cream-2 mt-2 max-w-[62ch] text-[15px]">
              The same name in two chats is one person. Switch off anyone who doesn&rsquo;t want to be roasted; the Roaster
              will refuse to write about them.
            </p>
            <table className="mt-4 w-full border-collapse">
              <thead>
                <tr className="border-line text-cream-3 border-b text-left text-sm">
                  <th scope="col" className="pb-2 font-semibold">Person</th>
                  <th scope="col" className="pb-2 pr-4 text-right font-semibold">Messages</th>
                  <th scope="col" className="hidden pb-2 pr-4 text-right font-semibold sm:table-cell">Chats</th>
                  <th scope="col" className="pb-2 pr-4 font-semibold">Roasts</th>
                  <th scope="col" className="pb-2"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {(allPeople ? people : people.slice(0, PEOPLE_SHOWN)).map((p) => (
                  <PersonRow key={p.id} p={p} />
                ))}
              </tbody>
            </table>
            {people.length > PEOPLE_SHOWN && (
              <Button variant="secondary" size="sm" className="mt-4" onClick={() => setAllPeople((v) => !v)}>
                {allPeople ? "Show the most active only" : `Show all ${people.length} people`}
              </Button>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
