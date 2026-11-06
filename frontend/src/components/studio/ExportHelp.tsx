"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

const STEPS = {
  android: ["Open the chat", "Tap the three dots", "More", "Export chat", "Include media"],
  iphone: ["Open the chat", "Tap the chat name", "Export chat", "Attach media", "Save to Files"],
} as const;

/** The exact WhatsApp menu path, per phone, as a row of steps. */
export function ExportHelp() {
  const [os, setOs] = useState<keyof typeof STEPS>("android");
  return (
    <div>
      <div role="tablist" aria-label="Your phone" className="bg-night-2 border-line inline-flex rounded-full border p-1">
        {(["android", "iphone"] as const).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={os === k}
            onClick={() => setOs(k)}
            className={`h-8 rounded-full px-4 text-sm font-semibold transition-colors ${
              os === k ? "on-lime bg-lime text-night" : "text-cream-2 hover:text-cream"
            }`}
          >
            {k === "android" ? "Android" : "iPhone"}
          </button>
        ))}
      </div>
      <ol role="tabpanel" className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-2">
        {STEPS[os].map((s, i) => (
          <li key={s} className="flex items-center gap-1">
            <span className="border-line-strong rounded-full border px-3 py-1.5 text-sm text-cream">{s}</span>
            {i < STEPS[os].length - 1 && <ChevronRight aria-hidden className="text-cream-3 size-4" />}
          </li>
        ))}
      </ol>
    </div>
  );
}
