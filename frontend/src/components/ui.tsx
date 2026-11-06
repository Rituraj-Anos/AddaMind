import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { initials, toneFor } from "@/lib/format";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-full font-semibold whitespace-nowrap transition-colors " +
  "duration-150 active:translate-y-px disabled:opacity-50 disabled:pointer-events-none";
const VARIANT: Record<Variant, string> = {
  primary: "on-lime bg-lime text-night hover:bg-lime-2",
  secondary: "border border-line-strong text-cream hover:border-cream hover:bg-night-3",
  ghost: "text-cream-2 hover:text-cream hover:bg-night-3",
  danger: "bg-alarm text-night hover:bg-alarm-2",
};
const SIZE = { sm: "h-8 px-3.5 text-sm", md: "h-10 px-5 text-[15px]", icon: "size-10" } as const;

export function buttonClass(variant: Variant = "primary", size: keyof typeof SIZE = "md", extra = "") {
  return `${BASE} ${VARIANT[variant]} ${SIZE[size]} ${extra}`;
}

export function Button({
  variant = "primary",
  size = "md",
  busy,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof SIZE; busy?: boolean }) {
  return (
    <button {...rest} disabled={rest.disabled || busy} className={buttonClass(variant, size, className)}>
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner({ className = "size-4" }: { className?: string }) {
  return <LoaderCircle aria-hidden className={`${className} animate-spin motion-reduce:animate-none`} />;
}

/** A person's circle with their initials. Quiet by default; "you" is lime, and `tone` colours a person in charts. */
export function Avatar({
  name,
  id,
  size = 36,
  me = false,
  tone = false,
}: {
  name: string;
  id: number;
  size?: number;
  me?: boolean;
  tone?: boolean;
}) {
  const colour = me ? "bg-lime text-night" : tone ? `${toneFor(id)} text-night` : "bg-night-3 text-cream";
  return (
    <span
      aria-hidden
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      className={`${colour} inline-flex shrink-0 items-center justify-center rounded-full font-bold`}
    >
      {initials(name)}
    </span>
  );
}

export function Chip({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "lime" | "pink" | "alarm" }) {
  const t = {
    plain: "border border-line-strong text-cream-2",
    lime: "bg-lime text-night",
    pink: "bg-pink text-night",
    alarm: "bg-alarm text-night",
  }[tone];
  return <span className={`${t} inline-flex h-6 items-center rounded-full px-2.5 text-xs font-semibold`}>{children}</span>;
}
