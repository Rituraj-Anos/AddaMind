import type { AgentKey } from "@/lib/agent";

/** Each agent's accent and copy. Tailwind classes are written out whole so the build keeps them. */
export const AGENTS: Record<
  AgentKey,
  { name: string; short: string; job: string; bg: string; text: string; border: string; band: "lime" | "pink" | "cream" | "ice" }
> = {
  analyzer: {
    name: "Deep Analyzer",
    short: "Analyze",
    job: "Who drives the chat, how the mood moved, who replies to whom.",
    bg: "bg-lime",
    text: "text-lime",
    border: "border-lime",
    band: "lime",
  },
  roaster: {
    name: "Roaster",
    short: "Roast",
    job: "Playful roasts of habits in the chat. Never looks, money, family or identity.",
    bg: "bg-pink",
    text: "text-pink",
    border: "border-pink",
    band: "pink",
  },
  recall: {
    name: "Memory Recall",
    short: "Recall",
    job: "When did we, who said, what was the plan. Answered with the date.",
    bg: "bg-ice",
    text: "text-ice",
    border: "border-ice",
    band: "ice",
  },
  reply: {
    name: "Reply Giver",
    short: "Reply",
    job: "Three to five replies in your own style, ready to copy.",
    bg: "bg-cream",
    text: "text-cream",
    border: "border-cream",
    band: "cream",
  },
};

export const ORDER: AgentKey[] = ["analyzer", "roaster", "recall", "reply"];
