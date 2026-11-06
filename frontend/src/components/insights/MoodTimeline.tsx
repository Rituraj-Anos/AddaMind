"use client";

import { useMemo, useState } from "react";
import type { ChatMemory, MemoryEvent } from "@/lib/types";

const W = 1000;
const H = 300;
const PAD = { l: 44, r: 20, t: 24, b: 56 };

const monthName = (m: string) => new Date(m + "-01T00:00").toLocaleString("en-GB", { month: "short" });
const year = (m: string) => m.slice(0, 4);

/** Monthly mood as a line, events pinned under their month. Clicking a pin or a month shows what happened. */
export function MoodTimeline({ memory, onOpen }: { memory: ChatMemory; onOpen: (messageId: number) => void }) {
  const mood = memory.mood;
  const byMonth = useMemo(() => {
    const m = new Map<string, MemoryEvent[]>();
    for (const e of memory.timeline) m.set(e.month, [...(m.get(e.month) ?? []), e]);
    return m;
  }, [memory.timeline]);
  const lowest = mood.reduce((a, b) => (b.mood < a.mood ? b : a), mood[0]);
  const [picked, setPicked] = useState<string>(lowest?.month ?? "");

  if (mood.length < 2) return <p className="text-cream-3 text-[15px]">Not enough months yet to draw a mood line.</p>;

  const x = (i: number) => PAD.l + (i * (W - PAD.l - PAD.r)) / (mood.length - 1);
  const y = (v: number) => PAD.t + ((1 - v) / 2) * (H - PAD.t - PAD.b);
  const line = mood.map((m, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(m.mood).toFixed(1)}`).join(" ");
  const area = `${line} L${x(mood.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const cur = mood.find((m) => m.month === picked) ?? mood[0];
  const events = byMonth.get(cur.month) ?? [];

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <figure className="min-w-0">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Mood by month, from -1 to 1">
          {[1, 0.5, 0, -0.5, -1].map((v) => (
            <g key={v}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className={v === 0 ? "stroke-line-strong" : "stroke-line"} strokeDasharray={v === 0 ? "" : "4 6"} />
              <text x={PAD.l - 12} y={y(v) + 4} textAnchor="end" className="fill-cream-3 font-mono text-[12px]">
                {v > 0 ? `+${v}` : v}
              </text>
            </g>
          ))}
          <path d={area} className="fill-lime/10" />
          <path d={line} fill="none" className="stroke-lime" strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" />
          {mood.map((m, i) => {
            const on = m.month === cur.month;
            const ev = byMonth.get(m.month)?.length ?? 0;
            return (
              <g key={m.month}>
                <line x1={x(i)} x2={x(i)} y1={y(m.mood)} y2={H - PAD.b + 8} className={on ? "stroke-cream-3" : "stroke-transparent"} strokeDasharray="2 4" />
                <circle cx={x(i)} cy={y(m.mood)} r={on ? 8 : 5} className={m.mood < 0 ? "fill-pink" : "fill-lime"} />
                {ev > 0 && <circle cx={x(i)} cy={H - PAD.b + 14} r={on ? 6 : 4} className={on ? "fill-cream" : "fill-cream-3"} />}
                <text x={x(i)} y={H - 12} textAnchor="middle" className={`font-sans text-[13px] ${on ? "fill-cream font-semibold" : "fill-cream-3"}`}>
                  {monthName(m.month)}
                </text>
                {(i === 0 || year(m.month) !== year(mood[i - 1].month)) && (
                  <text x={x(i)} y={H - 30} textAnchor="middle" className="fill-cream-3 font-mono text-[11px]">
                    {year(m.month)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {/* The clickable months, as real buttons over the chart for keyboard and screen readers. */}
        <div role="tablist" aria-label="Months" className="mt-3 flex flex-wrap gap-1.5">
          {mood.map((m) => (
            <button
              key={m.month}
              role="tab"
              aria-selected={m.month === cur.month}
              onClick={() => setPicked(m.month)}
              className={`h-8 rounded-full px-3 text-sm font-semibold transition-colors ${
                m.month === cur.month ? "bg-cream text-night" : "text-cream-2 hover:bg-night-3 hover:text-cream"
              }`}
            >
              {monthName(m.month)} {m.month.slice(2, 4)}
              {byMonth.get(m.month)?.length ? <span className="ml-1 opacity-60">{byMonth.get(m.month)!.length}</span> : null}
            </button>
          ))}
        </div>
      </figure>

      <div role="tabpanel" aria-live="polite" className="min-w-0">
        <p className="text-cream-3 text-sm">
          {new Date(cur.month + "-01T00:00").toLocaleString("en-GB", { month: "long", year: "numeric" })},{" "}
          {cur.messages.toLocaleString("en-IN")} messages
        </p>
        <p className={`display mt-2 text-[56px] leading-none ${cur.mood < 0 ? "text-pink" : "text-lime"}`}>
          {cur.mood > 0 ? "+" : ""}
          {cur.mood.toFixed(2)}
        </p>
        <p className="text-cream-2 mt-3 text-[16px] leading-relaxed">{cur.reason}</p>
        {events.length > 0 && (
          <ul className="border-line mt-6 border-t">
            {events.map((e) => (
              <li key={e.title + e.date} className="border-line border-b py-4">
                <p className="text-cream-3 font-mono text-[12px]">{e.date}</p>
                <p className="mt-1 text-[17px] font-semibold text-cream">{e.title}</p>
                <p className="text-cream-2 mt-1 text-[15px] leading-snug">{e.detail}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {e.message_ids.slice(0, 3).map((id, k) => (
                    <button
                      key={id}
                      onClick={() => onOpen(id)}
                      className="bg-night-3 hover:bg-lime hover:text-night rounded-full px-3 py-1 text-[13px] font-semibold text-cream transition-colors"
                    >
                      Message {k + 1}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
