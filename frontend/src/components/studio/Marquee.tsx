/** Four-point spark between marquee items: an authored mark, not a glyph. */
function Spark() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="size-3.5 shrink-0 fill-current">
      <path d="M8 0c.6 4.2 3.8 7.4 8 8-4.2.6-7.4 3.8-8 8-.6-4.2-3.8-7.4-8-8 4.2-.6 7.4-3.8 8-8z" />
    </svg>
  );
}

/** A running line of what is happening, in the display face. Decorative: the same facts are in the stage list. */
export function Marquee({
  items,
  tone = "lime",
  seconds = 36,
  size = 22,
}: {
  items: string[];
  tone?: "lime" | "pink" | "cream" | "ice";
  seconds?: number;
  size?: number;
}) {
  const band = { lime: "bg-lime", pink: "bg-pink", cream: "bg-cream", ice: "bg-ice" }[tone];
  // Enough copies that one half is wider than the viewport, then two halves for a seamless loop.
  const half = Array.from({ length: Math.max(2, Math.ceil(10 / Math.max(items.length, 1))) }, () => items).flat();
  const run = (key: string) => (
    <div key={key} className="flex shrink-0 items-center text-night">
      {half.map((t, i) => (
        <span key={i} className="flex items-center">
          <span className="display px-5 leading-none" style={{ fontSize: size }}>
            {t}
          </span>
          <Spark />
        </span>
      ))}
    </div>
  );
  return (
    <div aria-hidden className={`marquee ${band} overflow-hidden py-3`}>
      <div className="marquee-track" style={{ ["--marquee-speed" as string]: `${seconds}s` }}>
        {run("a")}
        {run("b")}
      </div>
    </div>
  );
}
