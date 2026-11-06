const num = new Intl.NumberFormat("en-IN");
export const formatCount = (n: number) => num.format(n);

export function formatBytes(n: number): string {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`;
  return `${(n / 1024 ** 3).toFixed(1)} GB`;
}

const monthYear = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" });
const dayMonthYear = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** Backend timestamps are naive local strings ("2025-03-14 04:12:00"); read them without a time zone shift. */
export function parseTs(ts: string): Date {
  return new Date(ts.replace(" ", "T"));
}

export const formatDay = (ts: string) => dayMonthYear.format(parseTs(ts));

export function formatRange(first: string | null, last: string | null): string {
  if (!first || !last) return "No messages yet";
  const a = monthYear.format(parseTs(first));
  const b = monthYear.format(parseTs(last));
  return a === b ? a : `${a} to ${b}`;
}

export function initials(name: string): string {
  const parts = name.replace(/[+•\d()\-\s]+/g, " ").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "#";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

/** Stable accent for a person, from the four palette colours. */
const TONES = ["bg-lime", "bg-pink", "bg-cream", "bg-ice"] as const;
export const toneFor = (id: number) => TONES[id % TONES.length];

/** "WhatsApp Chat with College Friends.zip" -> "College Friends"; iOS "WhatsApp Chat - Shrimant.zip" -> "Shrimant". */
export function titleFromFile(name: string): string | null {
  const stem = name.replace(/\.(zip|txt)$/i, "").replace(/\s*\(\d+\)$/, "");
  const m = stem.match(/^WhatsApp Chat\s*(?:with|-|–)\s*(.+)$/i);
  return m ? m[1].trim() : null;
}

export const percent = (share: number) => `${Math.round(share * 1000) / 10}%`;

export function plural(n: number, one: string, many = one + "s"): string {
  return `${formatCount(n)} ${n === 1 ? one : many}`;
}
