"use client";

import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { ChartSpline, FolderOpen, MessageCircleQuestion, Menu, Sparkles, Users, WifiOff, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { API_URL } from "@/lib/api";
import { plural } from "@/lib/format";
import { Button, Spinner } from "../ui";
import { useStudio } from "./StudioProvider";

function Wordmark() {
  return (
    <Link href="/studio" className="display block text-[30px] text-cream">
      AddaMind
    </Link>
  );
}

function NavLink({ href, icon, children, exact }: { href: string; icon: ReactNode; children: ReactNode; exact?: boolean }) {
  const path = usePathname();
  const active = exact ? path === href : path === href || path.startsWith(href + "/");
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`flex h-10 items-center gap-3 rounded-full px-4 text-[15px] font-medium transition-colors ${
        active ? "bg-cream text-night" : "text-cream-2 hover:bg-night-3 hover:text-cream"
      }`}
    >
      {icon}
      {children}
    </Link>
  );
}

function RailBody() {
  const { project, pid } = useStudio();
  return (
    <div className="flex h-full flex-col gap-7 overflow-y-auto px-4 py-5">
      <div className="px-2">
        <Wordmark />
        <p className="text-cream-3 mt-1 text-sm">Every adda, remembered.</p>
      </div>

      <nav aria-label="Studio" className="flex flex-col gap-1">
        <NavLink href="/studio" exact icon={<FolderOpen aria-hidden className="size-[18px]" />}>
          All projects
        </NavLink>
        {pid !== null && project && (
          <>
            <NavLink href={`/studio/${pid}`} exact icon={<Users aria-hidden className="size-[18px]" />}>
              Chats and people
            </NavLink>
            <NavLink href={`/studio/${pid}/ask`} icon={<MessageCircleQuestion aria-hidden className="size-[18px]" />}>
              Ask the agents
            </NavLink>
            <NavLink href={`/studio/${pid}/insights`} icon={<ChartSpline aria-hidden className="size-[18px]" />}>
              Insights
            </NavLink>
            <NavLink href={`/studio/${pid}/wrapped`} icon={<Sparkles aria-hidden className="size-[18px]" />}>
              Wrapped
            </NavLink>
          </>
        )}
      </nav>

      {pid !== null && project && (
        <section aria-labelledby="rail-project" className="min-h-0">
          <h2 id="rail-project" className="mb-2 truncate px-3 text-[15px] font-semibold text-cream">
            {project.name}
          </h2>
          {project.chats.length === 0 ? (
            <p className="text-cream-3 px-3 text-sm">No chats yet. Upload one to start.</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {project.chats.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/studio/${pid}/ask?chat=${c.id}`}
                    className="hover:bg-night-3 flex items-center justify-between gap-3 rounded-2xl px-3 py-2 transition-colors"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[15px] text-cream">{c.title}</span>
                      <span className="text-cream-3 block text-[13px]">
                        {c.kind === "group" ? "Group" : "One to one"}, {plural(c.message_count, "message")}
                      </span>
                    </span>
                    {c.status === "processing" && (
                      <span className="text-lime shrink-0">
                        <Spinner className="size-4" />
                        <span className="sr-only">Processing</span>
                      </span>
                    )}
                    {c.status === "failed" && <span className="text-alarm shrink-0 text-[13px] font-semibold">Failed</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function LoadingPage() {
  return (
    <div role="status" aria-label="Loading" className="mx-auto max-w-6xl px-6 py-14 lg:px-12">
      <div className="skeleton h-14 w-72 rounded-2xl" />
      <div className="skeleton mt-4 h-4 w-96 max-w-full" />
      <div className="mt-12 grid gap-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-16 w-full rounded-2xl" />
        ))}
      </div>
    </div>
  );
}

function Offline() {
  const { retry, error } = useStudio();
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-5 px-6 py-20">
      <WifiOff aria-hidden className="text-pink size-8" />
      <h1 className="display text-[48px] text-cream">The server isn&rsquo;t answering</h1>
      <p className="text-cream-2">
        AddaMind couldn&rsquo;t reach <span className="font-semibold text-cream">{API_URL}</span>. Start the API from
        the project folder, then try again.
      </p>
      <pre className="bg-night-2 border-line overflow-x-auto rounded-2xl border p-4 font-mono text-[13px] text-cream-2">
        .\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --port 8000
      </pre>
      {error && <p className="text-cream-3 text-sm">{error}</p>}
      <div>
        <Button onClick={retry}>Try again</Button>
      </div>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { status } = useStudio();
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const [openedAt, setOpenedAt] = useState(path);
  // Navigating from inside the drawer closes it (state adjusted during render, not in an effect).
  if (openedAt !== path) {
    setOpenedAt(path);
    setOpen(false);
  }
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <MotionConfig reducedMotion="user">
      <a
        href="#main"
        className="on-lime bg-lime text-night fixed top-3 left-3 z-50 -translate-y-20 rounded-full px-4 py-2 font-semibold focus:translate-y-0"
      >
        Skip to content
      </a>
      <div className="min-h-dvh lg:grid lg:grid-cols-[18rem_1fr]">
        <aside className="border-line bg-night sticky top-0 hidden h-dvh border-r lg:block">
          <RailBody />
        </aside>

        <header className="border-line bg-night sticky top-0 z-30 flex h-14 items-center justify-between border-b px-4 lg:hidden">
          <Wordmark />
          <button
            aria-label="Open menu"
            aria-expanded={open}
            onClick={() => setOpen(true)}
            className="hover:bg-night-3 grid size-10 place-items-center rounded-full"
          >
            <Menu aria-hidden className="size-5" />
          </button>
        </header>

        <AnimatePresence>
          {open && (
            <>
              <motion.div
                className="bg-scrim fixed inset-0 z-40 lg:hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setOpen(false)}
              />
              <motion.aside
                role="dialog"
                aria-label="Menu"
                className="bg-night border-line fixed inset-y-0 left-0 z-50 w-[19rem] max-w-[88vw] border-r lg:hidden"
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
              >
                <button
                  aria-label="Close menu"
                  onClick={() => setOpen(false)}
                  className="hover:bg-night-3 absolute top-3 right-3 grid size-10 place-items-center rounded-full"
                >
                  <X aria-hidden className="size-5" />
                </button>
                <RailBody />
              </motion.aside>
            </>
          )}
        </AnimatePresence>

        <main id="main" className="min-w-0">
          {status === "offline" ? (
            <Offline />
          ) : status === "loading" ? (
            <LoadingPage />
          ) : (
            children
          )}
        </main>
      </div>
    </MotionConfig>
  );
}
