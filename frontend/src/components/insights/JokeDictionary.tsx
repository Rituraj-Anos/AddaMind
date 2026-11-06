import type { InsideJoke } from "@/lib/types";

const TONES = ["bg-lime", "bg-pink", "bg-ice", "bg-cream"] as const;

/** The inside-joke dictionary: each joke the database confirmed, set like a dictionary entry. */
export function JokeDictionary({ jokes, onOpen }: { jokes: InsideJoke[]; onOpen: (messageId: number) => void }) {
  if (!jokes.length)
    return (
      <p className="text-cream-3 text-[15px]">
        No inside jokes confirmed yet. A phrase counts once at least two people reuse it in three different messages.
      </p>
    );
  return (
    <ol className="grid gap-5 lg:grid-cols-2">
      {jokes.map((j, i) => (
        <li key={j.phrase} className={`${TONES[i % 4]} text-night rounded-[28px] p-6 sm:p-8`}>
          <div className="flex items-start justify-between gap-4">
            <p className="display text-[44px] leading-[0.95] sm:text-[56px]">&ldquo;{j.phrase}&rdquo;</p>
            <p className="tabular shrink-0 text-right">
              <span className="display block text-[44px] leading-none">{j.uses}</span>
              <span className="text-[13px] font-semibold">uses</span>
            </p>
          </div>
          <p className="mt-4 text-[17px] leading-relaxed">{j.meaning}</p>
          <dl className="border-night/15 mt-6 grid grid-cols-3 border-t pt-4 text-[14px]">
            <div>
              <dt className="text-night/60">Started by</dt>
              <dd className="font-semibold">{j.started_by}</dd>
            </div>
            <div>
              <dt className="text-night/60">First said</dt>
              <dd className="tabular font-semibold">
                {new Date(j.first_date + "T00:00").toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
              </dd>
            </div>
            <div>
              <dt className="text-night/60">Picked up by</dt>
              <dd className="font-semibold">{j.people} people</dd>
            </div>
          </dl>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              onClick={() => onOpen(j.first_message_id)}
              className="bg-night text-cream hover:bg-night-3 rounded-full px-4 py-2 text-[14px] font-semibold transition-colors"
            >
              Where it started
            </button>
            {j.example_ids
              .filter((id) => id !== j.first_message_id)
              .map((id, k) => (
                <button
                  key={id}
                  onClick={() => onOpen(id)}
                  className="border-night/25 hover:bg-night hover:text-cream rounded-full border px-4 py-2 text-[14px] font-semibold transition-colors"
                >
                  Example {k + 1}
                </button>
              ))}
          </div>
        </li>
      ))}
    </ol>
  );
}
