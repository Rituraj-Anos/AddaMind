"use client";

import { Check, CircleAlert, X } from "lucide-react";
import { formatBytes, formatCount, plural } from "@/lib/format";
import type { Job, JobInfo, JobStage } from "@/lib/types";
import { Spinner } from "../ui";
import type { Upload } from "./StudioProvider";

const STAGES: { key: Exclude<JobStage, "queued" | "done">; label: string; what: string }[] = [
  { key: "parse", label: "Read the messages", what: "Every line, person and date, kept on this server." },
  { key: "media", label: "Photos, voice notes and videos", what: "Described and transcribed, so they can be searched." },
  { key: "index", label: "Search index", what: "Keyword and meaning search over every conversation." },
  { key: "memory", label: "Memory", what: "Each month summed up: events, mood, inside jokes." },
  { key: "personas", label: "Personas", what: "How the most active people write and joke." },
];

/** The same track before anything is uploaded: what each stage will do. */
export function StagePreview() {
  return (
    <section aria-labelledby="stages-title">
      <h2 id="stages-title" className="text-[17px] font-semibold text-cream">
        What happens to an upload
      </h2>
      <ol className="mt-5 grid gap-5 sm:grid-cols-5 sm:gap-2">
        {STAGES.map((s, idx) => (
          <li key={s.key} className="flex gap-3 sm:flex-col sm:gap-3">
            <div className="flex items-center gap-2 sm:w-full">
              <span className="border-line-strong text-cream-2 tabular grid size-7 shrink-0 place-items-center rounded-full border text-[13px] font-semibold">
                {idx + 1}
              </span>
              <span
                aria-hidden
                className={`bg-line hidden h-0.5 flex-1 rounded-full sm:block ${idx === STAGES.length - 1 ? "invisible" : ""}`}
              />
            </div>
            <div className="min-w-0 pr-3">
              <p className="text-[15px] text-cream">{s.label}</p>
              <p className="text-cream-3 mt-0.5 text-sm">{s.what}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** What a finished stage found, from the counts the backend reports. */
function detail(stage: (typeof STAGES)[number]["key"], i: JobInfo): string | null {
  switch (stage) {
    case "parse":
      if (i.messages === undefined) return null;
      return i.skipped
        ? `${formatCount(i.inserted ?? 0)} new of ${formatCount(i.messages)}; ${formatCount(i.skipped)} were already here`
        : plural(i.messages, "message");
    case "media": {
      const done = i.media_done ?? 0;
      if (i.media_pending) return `${plural(i.media_pending, "file")} waiting: media analysis is off`;
      if (!done && !i.media_skipped && !i.media_failed) return i.media_saved === 0 ? "No media in this export" : null;
      const parts = [`${formatCount(done)} analysed`];
      if (i.media_skipped) parts.push(`${formatCount(i.media_skipped)} skipped (stickers)`);
      if (i.media_failed) parts.push(`${formatCount(i.media_failed)} failed`);
      return parts.join(", ");
    }
    case "index":
      return i.passages === undefined ? null : `${plural(i.passages, "passage")}, ${formatCount(i.embedded ?? 0)} with meaning search`;
    case "memory":
      if (i.memory === "off") return "Off on this server";
      if (i.months_summarised === undefined) return null;
      return `${plural(i.months_summarised, "month")}, ${plural(i.events ?? 0, "event")}, ${plural(i.inside_jokes ?? 0, "inside joke")}`;
    case "personas":
      return i.personas === undefined ? null : plural(i.personas, "persona");
  }
}

type StepState = "done" | "now" | "wait" | "failed";

function stepState(job: Job, idx: number): StepState {
  if (job.status === "done") return "done";
  const cur = STAGES.findIndex((s) => s.key === job.stage);
  if (cur < 0) return "wait"; // queued
  if (idx < cur) return "done";
  if (idx === cur) return job.status === "failed" ? "failed" : "now";
  return "wait";
}

function StepMark({ state }: { state: StepState }) {
  const base = "grid size-7 shrink-0 place-items-center rounded-full";
  if (state === "done")
    return (
      <span className={`${base} bg-lime text-night`}>
        <Check aria-hidden className="size-4" strokeWidth={3} />
      </span>
    );
  if (state === "now")
    return (
      <span className={`${base} border-lime text-lime border-2`}>
        <Spinner className="size-3.5" />
      </span>
    );
  if (state === "failed")
    return (
      <span className={`${base} bg-alarm text-night`}>
        <X aria-hidden className="size-4" strokeWidth={3} />
      </span>
    );
  return <span className={`${base} border-line-strong border`} />;
}

const STATE_TEXT: Record<StepState, string> = { done: "done", now: "in progress", wait: "waiting", failed: "failed" };

export function JobTrack({ job }: { job: Job }) {
  const title = job.info.title ?? job.filename;
  const running = job.status === "running" || job.status === "queued";
  return (
    <article aria-label={`Upload of ${title}`} className="bg-night-2 border-line rounded-2xl border p-5 sm:p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h3 className="text-[17px] font-semibold text-cream">{title}</h3>
        <p className="text-cream-3 text-sm" aria-live="polite">
          {job.status === "done"
            ? job.info.created === false
              ? "Merged into the existing chat"
              : "Ready to ask"
            : job.status === "failed"
              ? "Stopped"
              : job.status === "queued"
                ? "Waiting to start"
                : "Working"}
        </p>
      </header>

      <ol className="mt-5 grid gap-3 sm:grid-cols-5 sm:gap-2">
        {STAGES.map((s, idx) => {
          const st = stepState(job, idx);
          const d = st === "done" || st === "failed" ? detail(s.key, job.info) : null;
          const progress = st === "now" && job.total > 0 ? job.done / job.total : null;
          return (
            <li key={s.key} className="flex gap-3 sm:flex-col sm:gap-2">
              <div className="flex items-center gap-2 sm:w-full">
                <StepMark state={st} />
                <span
                  aria-hidden
                  className={`hidden h-0.5 flex-1 rounded-full sm:block ${idx === STAGES.length - 1 ? "invisible" : st === "done" ? "bg-lime" : "bg-line"}`}
                />
              </div>
              <div className="min-w-0 pr-2">
                <p className={`text-[15px] ${st === "wait" ? "text-cream-3" : "text-cream"}`}>
                  {s.label}
                  <span className="sr-only">: {STATE_TEXT[st]}</span>
                </p>
                {progress !== null && (
                  <p className="text-lime tabular text-sm">
                    {formatCount(job.done)} of {formatCount(job.total)}
                  </p>
                )}
                {st === "now" && progress === null && <p className="text-cream-3 text-sm">Starting</p>}
                {d && <p className="text-cream-2 text-sm">{d}</p>}
              </div>
            </li>
          );
        })}
      </ol>

      {job.status === "failed" && (
        <p role="alert" className="text-alarm mt-5 flex items-start gap-2 text-sm">
          <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            {job.error ?? "Processing stopped."} {job.chat_id ? "What was read so far is kept." : "Nothing was saved."}
          </span>
        </p>
      )}
      {running && job.stage === "media" && (
        <p className="text-cream-3 mt-5 text-sm">
          Media is the slow part: free model limits allow about 20 files a minute. You can ask questions about the text
          meanwhile.
        </p>
      )}
    </article>
  );
}

/** A file still on its way to the server. */
export function UploadRow({ u, onDismiss }: { u: Upload; onDismiss: () => void }) {
  return (
    <article aria-label={`Uploading ${u.name}`} className="bg-night-2 border-line rounded-2xl border p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h3 className="min-w-0 truncate text-[17px] font-semibold text-cream">{u.name}</h3>
        <p className="text-cream-3 tabular text-sm">
          {u.error ? "Not uploaded" : `${Math.round(u.progress * 100)}% of ${formatBytes(u.size)}`}
        </p>
      </div>
      {u.error ? (
        <div className="mt-3 flex items-center justify-between gap-4">
          <p role="alert" className="text-alarm text-sm">
            {u.error}
          </p>
          <button onClick={onDismiss} className="text-cream-2 hover:text-cream text-sm font-semibold underline">
            Dismiss
          </button>
        </div>
      ) : (
        <div className="mt-4 flex items-center gap-4">
          <div className="bg-line h-1.5 flex-1 overflow-hidden rounded-full">
            <div
              className="bg-lime h-full origin-left rounded-full transition-transform duration-200"
              style={{ transform: `scaleX(${u.progress})` }}
            />
          </div>
          {u.cancel && (
            <button onClick={u.cancel} className="text-cream-2 hover:text-cream text-sm font-semibold underline">
              Cancel
            </button>
          )}
        </div>
      )}
    </article>
  );
}

/** Marquee lines for whatever is running right now, built from real stage counts. */
export function liveLines(jobs: Job[]): string[] {
  const out: string[] = [];
  for (const j of jobs) {
    if (j.status !== "running" && j.status !== "queued") continue;
    const t = j.info.title ?? j.filename.replace(/\.(zip|txt)$/i, "");
    const n = j.total ? ` ${formatCount(j.done)} of ${formatCount(j.total)}` : "";
    out.push(
      {
        queued: `${t} queued`,
        parse: `Reading ${t}${n}`,
        media: `Looking at ${t} media${n}`,
        index: `Indexing ${t}${n}`,
        memory: `Remembering ${t} month by month${n}`,
        personas: `Getting to know ${t}${n}`,
        done: `${t} done`,
      }[j.stage],
    );
  }
  return out;
}
