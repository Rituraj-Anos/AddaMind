/** A tool's result drawn small: bars for stats, a line for mood, pairs for the reply graph, counts for search. */

type R = Record<string, unknown>;
const isObj = (v: unknown): v is R => !!v && typeof v === "object" && !Array.isArray(v);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const first = (s: string) => (s.startsWith("+") ? s : s.split(" ")[0]);

function Bars({ rows }: { rows: { label: string; value: number; text: string }[] }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <ul className="grid gap-1.5">
      {rows.map((r, i) => (
        <li key={r.label} className="grid grid-cols-[5.5rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm">
          <span className="truncate text-cream">{r.label}</span>
          <span className="bg-night-3 h-2 overflow-hidden rounded-full">
            <span
              className={`block h-full origin-left rounded-full ${i ? "bg-cream-2" : "bg-lime"}`}
              style={{ transform: `scaleX(${r.value / max})` }}
            />
          </span>
          <span className="tabular text-cream-2 text-right">{r.text}</span>
        </li>
      ))}
    </ul>
  );
}

function MoodLine({ months }: { months: { month: string; mood: number }[] }) {
  if (months.length < 2) return null;
  const W = 320, H = 72, pad = 6;
  const x = (i: number) => pad + (i * (W - 2 * pad)) / (months.length - 1);
  const y = (v: number) => H / 2 - (v * (H / 2 - pad));
  const d = months.map((m, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(m.mood).toFixed(1)}`).join(" ");
  const low = months.reduce((a, b) => (b.mood < a.mood ? b : a));
  const high = months.reduce((a, b) => (b.mood > a.mood ? b : a));
  const label = (m: string) => new Date(m + "-01T00:00").toLocaleString("en-GB", { month: "short" });
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[72px] w-full max-w-[320px]" role="img" aria-label="Mood by month">
        <line x1={pad} x2={W - pad} y1={H / 2} y2={H / 2} className="stroke-line" strokeDasharray="3 4" />
        <path d={d} fill="none" className="stroke-lime" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        {months.map((m, i) => (
          <circle key={m.month} cx={x(i)} cy={y(m.mood)} r={m === low || m === high ? 4 : 2.5} className={m === low ? "fill-pink" : "fill-lime"} />
        ))}
      </svg>
      <figcaption className="text-cream-3 mt-1 text-sm">
        High in {label(high.month)} ({high.mood > 0 ? "+" : ""}
        {high.mood}), low in {label(low.month)} ({low.mood})
      </figcaption>
    </figure>
  );
}

/** One-line summary, used in the row itself. */
export function summary(name: string, result: unknown): string {
  if (!isObj(result)) return typeof result === "string" ? result.slice(0, 80) : "Done";
  if (typeof result.error === "string") return result.error.slice(0, 120);
  switch (name) {
    case "search_messages": {
      const n = arr(result.results).length;
      return n ? `${n} message${n === 1 ? "" : "s"} found` : "Nothing found";
    }
    case "get_chat_stats": {
      const t = isObj(result.totals) ? result.totals : {};
      return `${Number(t.messages ?? 0).toLocaleString("en-IN")} messages, ${t.participants ?? 0} people`;
    }
    case "get_mood_series":
      return result.note ? String(result.note) : `${arr(result.series).reduce((n: number, s) => n + arr(isObj(s) ? s.months : []).length, 0)} months`;
    case "get_timeline":
      return result.note ? String(result.note) : `${arr(result.timelines).reduce((n: number, s) => n + arr(isObj(s) ? s.events : []).length, 0)} events`;
    case "get_reply_graph":
      return isObj(result.closest_pair) ? `Closest: ${arr(result.closest_pair.names).map((x) => first(String(x))).join(" and ")}` : "No replies yet";
    case "get_persona":
      return `${result.name}: ${result.group_role ?? ""}`;
    case "get_inside_jokes":
      return `${arr(result.jokes).length} inside jokes`;
    case "get_messages_around":
      return `${arr(result.lines).length} messages read`;
    case "list_chats":
      return `${arr(result.chats).length} chats`;
    case "list_participants":
      return `${arr(result.participants).length} people`;
    case "get_media":
      return result.result ? String(result.result).slice(0, 90) : String(result.media ?? result.status ?? "");
    default:
      return "Done";
  }
}

/** The drawn result, or null when the one-line summary says it all. */
export function ToolResult({ name, result }: { name: string; result: unknown }) {
  if (!isObj(result) || result.error) return null;
  if (name === "get_chat_stats") {
    const people = arr(result.people).filter(isObj).slice(0, 5);
    if (!people.length) return null;
    return (
      <Bars
        rows={people.map((p) => ({
          label: first(String(p.name)),
          value: Number(p.share),
          text: `${(Number(p.share) * 100).toFixed(1)}%`,
        }))}
      />
    );
  }
  if (name === "get_mood_series") {
    const s = arr(result.series).filter(isObj)[0];
    const months = arr(s?.months)
      .filter(isObj)
      .map((m) => ({ month: String(m.month), mood: Number(m.mood) }));
    return <MoodLine months={months} />;
  }
  if (name === "get_reply_graph") {
    const pairs = arr(result.strongest).slice(0, 4).map(String);
    return (
      <ul className="text-cream-2 grid gap-1 text-sm">
        {pairs.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    );
  }
  if (name === "get_inside_jokes") {
    const jokes = arr(result.jokes).filter(isObj).slice(0, 4);
    return (
      <ul className="flex flex-wrap gap-2">
        {jokes.map((j) => (
          <li key={String(j.phrase)} className="bg-night-3 rounded-full px-3 py-1 text-sm text-cream">
            &ldquo;{String(j.phrase)}&rdquo; <span className="text-cream-3">{String(j.uses)}x</span>
          </li>
        ))}
      </ul>
    );
  }
  if (name === "get_persona" && Array.isArray(result.catchphrases) && result.catchphrases.length) {
    return (
      <p className="text-cream-2 text-sm">
        Says: {arr(result.catchphrases).filter(isObj).map((c) => `"${c.phrase}"`).join(", ")}
      </p>
    );
  }
  return null;
}
