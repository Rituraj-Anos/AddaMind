/** The tilted example card on the start screen. Every figure is from the bundled demo chat
 * (data/demo/facts.json and its stats), and the card says the people are made up. */

function Receipt({ who, when, text, side = "left" }: { who: string; when: string; text: string; side?: "left" | "right" }) {
  return (
    <figure className={`max-w-[88%] ${side === "right" ? "ml-auto" : ""}`}>
      <blockquote
        className={`rounded-2xl px-3.5 py-2.5 text-[14px] leading-snug text-night ${
          side === "right" ? "bg-lime rounded-br-md" : "bg-bubble rounded-bl-md"
        }`}
      >
        {text}
      </blockquote>
      <figcaption className={`mt-1 text-[12px] text-night/60 ${side === "right" ? "text-right" : ""}`}>
        {who}, <time className="font-mono">{when}</time>
      </figcaption>
    </figure>
  );
}

export function SampleRead() {
  return (
    <div className="relative mx-auto w-full max-w-[26rem] pt-4 pb-6 lg:mx-0">
      {/* The sheet underneath gives the card its stack, like a printed report on a desk. */}
      <div aria-hidden className="bg-pink absolute inset-x-2 top-2 bottom-4 translate-x-5 rotate-[6deg] rounded-[28px]" />
      <article
        aria-label="Example of a first read, from the demo chat"
        className="bg-cream shadow-lift relative -rotate-[2.5deg] rounded-[28px] p-6 text-night sm:p-7"
      >
        <p className="text-[13px] font-semibold text-night/60">Demo chat, College Friends. Everyone in it is made up.</p>
        <h2 className="display mt-3 text-[40px] leading-[0.92]">Priya keeps this group going</h2>
        <p className="mt-3 text-[15px] leading-snug">
          She sent 572 of 3,466 messages and started 145 of the 429 conversations.
        </p>

        <dl className="mt-5 grid grid-cols-3 border-y border-night/15">
          {[
            ["Rohan", "voice notes"],
            ["Kabir", "up at 3 am"],
            ["Aditya", "went quiet"],
          ].map(([who, what], i) => (
            <div key={who} className={`py-3 ${i ? "border-l border-night/15 pl-3" : ""}`}>
              <dt className="display text-[24px] leading-none">{who}</dt>
              <dd className="mt-1 text-[13px] text-night/70">{what}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-5 flex flex-col gap-3">
          <Receipt who="Abhishek Kundu" when="14 Mar, 4:12" text="BHAI TICKETS GHAR PE BHOOL GAYA 😭😭 printout wala" />
          <Receipt who="Priya Sen" when="4:13" text="PNR se ho jayega, chill. Aadhaar hai na?" side="right" />
        </div>
      </article>
    </div>
  );
}
