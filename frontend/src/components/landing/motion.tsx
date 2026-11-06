"use client";

import Lenis from "lenis";
import { useReducedMotion } from "framer-motion";
import { useEffect, type CSSProperties, type ReactNode } from "react";

/** Lenis smooth scrolling for the landing page; anchors (#how, #sample) glide too. Off under reduced motion. */
export function SmoothScroll() {
  const reduce = useReducedMotion();
  useEffect(() => {
    if (reduce) return;
    const lenis = new Lenis({ autoRaf: true, anchors: { offset: -72 }, lerp: 0.1 });
    return () => lenis.destroy();
  }, [reduce]);
  return null;
}

/** Fades and lifts content in as it scrolls into view, driven by CSS scroll timelines (globals.css .reveal).
 * Content is visible by default: without JS, without support, and under reduced motion. */
export function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <div className={`reveal ${className}`} style={{ "--reveal-start": `${Math.round(delay * 60)}%` } as CSSProperties}>
      {children}
    </div>
  );
}

/** A bar that fills to `value` (0 to 1) as it scrolls into view (globals.css .fill). */
export function FillBar({ value, className }: { value: number; className: string }) {
  return <span className={`fill block h-full origin-left ${className}`} style={{ "--fill": value } as CSSProperties} />;
}
