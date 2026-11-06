"use client";

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Persona, ReplyGraph as Graph } from "@/lib/types";
import { Spinner } from "../ui";

interface N extends SimulationNodeDatum {
  id: number;
  name: string;
  is_me: boolean;
  messages: number;
  r: number;
}
interface L extends SimulationLinkDatum<N> {
  weight: number;
}

const W = 720;
const H = 560;
const first = (n: string) => (n.startsWith("+") ? n.slice(-4) : n.split(" ")[0]);

/** Laid out once, synchronously (300 ticks), so the graph appears settled and still: no jiggling on a projector. */
function layout(g: Graph): { nodes: N[]; links: L[] } {
  const max = Math.max(...g.nodes.map((n) => n.messages), 1);
  const nodes: N[] = g.nodes.map((n, i) => ({
    ...n,
    r: 10 + 26 * Math.sqrt(n.messages / max),
    x: W / 2 + Math.cos(i) * 120,
    y: H / 2 + Math.sin(i) * 120,
  }));
  // Pair both directions into one undirected line, keep the strongest 45.
  const pairs = new Map<string, L>();
  for (const e of g.edges) {
    const k = e.source < e.target ? `${e.source}-${e.target}` : `${e.target}-${e.source}`;
    const cur = pairs.get(k);
    if (cur) cur.weight += e.weight;
    else pairs.set(k, { source: e.source, target: e.target, weight: e.weight } as unknown as L);
  }
  const links = [...pairs.values()].sort((a, b) => b.weight - a.weight).slice(0, 45);
  const top = links[0]?.weight || 1;
  forceSimulation(nodes)
    .force("charge", forceManyBody().strength(-260))
    .force("link", forceLink<N, L>(links).id((d) => d.id).distance((l) => 210 - 120 * (l.weight / top)).strength((l) => 0.15 + 0.6 * (l.weight / top)))
    .force("center", forceCenter(W / 2, H / 2))
    // People with no strong lines would otherwise drift to the corners.
    .force("x", forceX(W / 2).strength(0.08))
    .force("y", forceY(H / 2).strength(0.1))
    .force("collide", forceCollide<N>().radius((d) => d.r + 8))
    .stop()
    .tick(300);
  for (const n of nodes) {
    n.x = Math.max(n.r + 4, Math.min(W - n.r - 4, n.x ?? 0));
    n.y = Math.max(n.r + 4, Math.min(H - n.r - 4, n.y ?? 0));
  }
  return { nodes, links };
}

function PersonaCard({ pid, cid, node }: { pid: number; cid: number; node: N }) {
  const [p, setP] = useState<Persona | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .persona(pid, node.id, cid)
      .then((x) => live && setP(x))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [pid, cid, node.id]);
  return (
    <div className="bg-cream text-night rounded-[24px] p-6">
      <p className="display text-[40px] leading-none">{node.name}</p>
      <p className="mt-1 text-[14px] text-night/70">{node.messages.toLocaleString("en-IN")} messages</p>
      {error && <p className="mt-4 text-[15px]">The persona isn&rsquo;t ready: {error}</p>}
      {!p && !error && (
        <p className="mt-4 flex items-center gap-2 text-[15px]">
          <Spinner /> Reading how they write (a few seconds the first time)
        </p>
      )}
      {p && (
        <>
          <p className="bg-night text-cream mt-4 inline-block rounded-full px-3 py-1 text-[13px] font-semibold">{p.group_role}</p>
          <p className="mt-4 text-[16px] leading-relaxed">{p.summary}</p>
          <p className="mt-3 text-[14px] leading-relaxed text-night/75">{p.communication_style}</p>
          {p.catchphrases.length > 0 && (
            <ul className="mt-4 flex flex-wrap gap-2">
              {p.catchphrases.map((c) => (
                <li key={c.phrase} className="border-night/20 rounded-full border px-3 py-1 text-[14px]">
                  &ldquo;{c.phrase}&rdquo; <span className="text-night/60">{c.uses}x</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/** Who replies to whom within 10 minutes, plus @mentions. Node size is activity; line weight is how often. */
export function ReplyGraph({ pid, cid, graph }: { pid: number; cid: number; graph: Graph }) {
  const { nodes, links } = useMemo(() => layout(graph), [graph]);
  const couple = graph.power_couple?.participant_ids ?? [];
  const [picked, setPicked] = useState<number | null>(couple[0] ?? nodes[0]?.id ?? null);
  const [hover, setHover] = useState<number | null>(null);
  const focus = hover ?? picked;
  const top = links[0]?.weight || 1;
  const node = nodes.find((n) => n.id === picked) ?? null;
  const near = (l: L) => focus !== null && ((l.source as N).id === focus || (l.target as N).id === focus);

  if (nodes.length < 2) return <p className="text-cream-3 text-[15px]">A graph needs at least two people.</p>;

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <figure className="bg-night-2 border-line min-w-0 rounded-[28px] border p-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Who replies to whom">
          {links.map((l, i) => {
            const s = l.source as N, t = l.target as N;
            const on = near(l);
            return (
              <line
                key={i}
                x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                strokeWidth={1 + 9 * (l.weight / top)}
                strokeLinecap="round"
                className={`transition-opacity duration-200 ${on ? "stroke-lime" : "stroke-cream-3"}`}
                opacity={focus === null ? 0.35 : on ? 0.9 : 0.08}
              />
            );
          })}
          {nodes.map((n) => {
            const on = n.id === focus;
            const linked = focus === null || on || links.some((l) => near(l) && ((l.source as N).id === n.id || (l.target as N).id === n.id));
            return (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                className="cursor-pointer"
                opacity={linked ? 1 : 0.3}
                onClick={() => setPicked(n.id)}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
              >
                <circle r={n.r} className={n.id === picked ? "fill-cream" : n.is_me ? "fill-lime" : couple.includes(n.id) ? "fill-pink" : "fill-night-3"} stroke="currentColor" />
                <text
                  y={n.r > 22 ? 5 : n.r + 16}
                  textAnchor="middle"
                  className={`font-sans text-[14px] font-semibold ${n.r > 22 && (n.id === picked || n.is_me || couple.includes(n.id)) ? "fill-night" : "fill-cream"}`}
                >
                  {first(n.name)}
                </text>
              </g>
            );
          })}
        </svg>
        <figcaption className="text-cream-3 flex flex-wrap gap-x-5 gap-y-1 px-4 pb-3 text-[13px]">
          <span className="flex items-center gap-1.5"><span className="bg-lime size-2.5 rounded-full" /> You</span>
          <span className="flex items-center gap-1.5"><span className="bg-pink size-2.5 rounded-full" /> Closest pair</span>
          <span>Bigger circle, more messages. Thicker line, more replies.</span>
        </figcaption>
      </figure>
      <div className="min-w-0">
        <label className="text-cream-3 text-sm" htmlFor="graph-person">
          Person
        </label>
        <select
          id="graph-person"
          value={picked ?? ""}
          onChange={(e) => setPicked(Number(e.target.value))}
          className="border-line-strong bg-night-2 mt-1 mb-4 block h-10 w-full rounded-full border px-4 text-[15px] font-semibold text-cream"
        >
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </select>
        {node && <PersonaCard key={node.id} pid={pid} cid={cid} node={node} />}
      </div>
    </div>
  );
}
