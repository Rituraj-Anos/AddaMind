"use client";

import { useParams, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, uploadChat } from "@/lib/api";
import { titleFromFile } from "@/lib/format";
import type { Job, Participant, Project, ProjectDetail } from "@/lib/types";

export interface Upload {
  id: string;
  name: string;
  size: number;
  /** 0 to 1 while the file is on its way to the server */
  progress: number;
  error?: string;
  cancel?: () => void;
}

interface Studio {
  /** loading: first request pending. offline: the API can't be reached. */
  status: "loading" | "ready" | "offline";
  error: string | null;
  projects: Project[];
  pid: number | null;
  project: ProjectDetail | null;
  /** The project id is in the URL but the server doesn't know it. */
  missing: boolean;
  people: Participant[];
  /** Running jobs, plus finished ones from the last few minutes. */
  jobs: Job[];
  uploads: Upload[];
  retry: () => void;
  createProject: (name: string) => Promise<Project>;
  removeProject: (pid: number) => Promise<void>;
  removeChat: (cid: number) => Promise<void>;
  addFiles: (files: File[]) => void;
  startWithFiles: (files: File[]) => Promise<Project>;
  renameProject: (name: string) => Promise<void>;
  dismissUpload: (id: string) => void;
  setMe: (participantId: number) => Promise<void>;
  setRoastOptOut: (participantId: number, optOut: boolean) => Promise<void>;
}

/** Everything loaded for one project, kept with its id so a stale response can't show under another project. */
interface Snapshot {
  pid: number;
  project: ProjectDetail | null;
  people: Participant[];
  jobs: Job[];
  missing: boolean;
}

const Ctx = createContext<Studio | null>(null);

export function useStudio(): Studio {
  const v = useContext(Ctx);
  if (!v) throw new Error("useStudio must be used inside StudioProvider");
  return v;
}

const POLL_MS = 1000;
const RECENT_MS = 15 * 60 * 1000;
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const isActive = (j: Job) => j.status === "queued" || j.status === "running";

export function StudioProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const params = useParams<{ pid?: string }>();
  const pid = params.pid && /^\d+$/.test(params.pid) ? Number(params.pid) : null;

  const [status, setStatus] = useState<Studio["status"]>("loading");
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const pidRef = useRef(pid);
  const activeRef = useRef(false);
  const pending = useRef<{ pid: number; files: File[] } | null>(null);

  useEffect(() => {
    pidRef.current = pid;
  }, [pid]);

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.offline) {
      setStatus("offline");
      setError(e.message);
    } else {
      setError(errText(e));
    }
  }, []);

  const loadProjects = useCallback(
    () =>
      api.projects().then(
        (ps) => {
          setProjects(ps);
          setStatus("ready");
          setError(null);
        },
        fail,
      ),
    [fail],
  );

  /** Everything that belongs to one project. A 404 marks it missing. */
  const loadProject = useCallback(
    (id: number) =>
      Promise.all([api.project(id), api.participants(id), api.jobs(id)]).then(
        ([project, people, all]) => {
          const now = Date.now();
          const jobs = all.filter(
            (j) =>
              isActive(j) ||
              now - new Date(j.updated_at).getTime() < (j.status === "failed" ? 4 * RECENT_MS : RECENT_MS),
          );
          activeRef.current = all.some(isActive) || project.chats.some((c) => c.status === "processing");
          setSnap({ pid: id, project, people, jobs, missing: false });
        },
        (e: unknown) => {
          if (e instanceof ApiError && e.status === 404) setSnap({ pid: id, project: null, people: [], jobs: [], missing: true });
          else fail(e);
        },
      ),
    [fail],
  );

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    activeRef.current = false;
    if (pid !== null) void loadProject(pid);
  }, [pid, loadProject]);

  // While anything is processing (or the server was unreachable), refresh once a second.
  useEffect(() => {
    if (pid === null) return;
    const t = setInterval(() => {
      if (!activeRef.current && status !== "offline") return;
      void loadProject(pid).then(() => {
        if (!activeRef.current) void loadProjects(); // the last refresh after work ends also updates counts
      });
    }, POLL_MS);
    return () => clearInterval(t);
  }, [pid, status, loadProject, loadProjects]);

  const retry = useCallback(() => {
    setStatus("loading");
    void loadProjects();
    if (pidRef.current !== null) void loadProject(pidRef.current);
  }, [loadProjects, loadProject]);

  const createProject = useCallback(
    async (name: string) => {
      const p = await api.createProject(name);
      await loadProjects();
      return p;
    },
    [loadProjects],
  );

  const removeProject = useCallback(
    async (id: number) => {
      await api.deleteProject(id);
      await loadProjects();
      if (pidRef.current === id) router.push("/studio");
    },
    [loadProjects, router],
  );

  const removeChat = useCallback(
    async (cid: number) => {
      const id = pidRef.current;
      if (id === null) return;
      await api.deleteChat(id, cid);
      await Promise.all([loadProject(id), loadProjects()]);
    },
    [loadProject, loadProjects],
  );

  const patchUpload = useCallback((id: string, patch: Partial<Upload>) => {
    setUploads((u) => u.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  }, []);

  const uploadTo = useCallback(
    (target: number, files: File[]) => {
      for (const file of files) {
        const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
        const bad = !/\.(txt|zip)$/i.test(file.name)
          ? "That isn't a WhatsApp export. Upload the .zip or .txt from Export chat."
          : file.size > 300 * 1024 * 1024
            ? "That file is over 300 MB. Export without media, or split the chat."
            : null;
        setUploads((u) => [...u, { id, name: file.name, size: file.size, progress: 0, error: bad ?? undefined }]);
        if (bad) continue;
        // The browser can fire progress events many times a second; redraw on whole-percent steps only.
        let shown = -1;
        const { promise, cancel } = uploadChat(target, file, (f) => {
          const pct = Math.floor(f * 100);
          if (pct !== shown) {
            shown = pct;
            patchUpload(id, { progress: f });
          }
        });
        patchUpload(id, { cancel });
        promise
          .then(async () => {
            setUploads((u) => u.filter((x) => x.id !== id));
            activeRef.current = true;
            await loadProject(target);
          })
          .catch((e: unknown) => {
            if (e instanceof ApiError && e.status === -1) setUploads((u) => u.filter((x) => x.id !== id));
            else patchUpload(id, { error: errText(e), cancel: undefined });
          });
      }
    },
    [loadProject, patchUpload],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      if (pidRef.current !== null) uploadTo(pidRef.current, files);
    },
    [uploadTo],
  );

  /** First drop on the start screen: make a project named after the chat and open it. The upload itself starts
   * from the project page (see the effect below), so the start screen never waits on it. */
  const startWithFiles = useCallback(
    async (files: File[]) => {
      const exports = files.filter((f) => /\.(txt|zip)$/i.test(f.name));
      if (!exports.length) throw new Error("That isn't a WhatsApp export. Drop the .zip or .txt from Export chat.");
      const p = await api.createProject(titleFromFile(exports[0].name) ?? "My chats");
      pending.current = { pid: p.id, files: exports };
      void loadProjects();
      router.push(`/studio/${p.id}`);
      return p;
    },
    [loadProjects, router],
  );

  useEffect(() => {
    const job = pending.current;
    if (job && pid === job.pid) {
      pending.current = null;
      uploadTo(job.pid, job.files);
    }
  }, [pid, uploadTo]);

  const renameProject = useCallback(
    async (name: string) => {
      const id = pidRef.current;
      if (id === null) return;
      await api.renameProject(id, name);
      await Promise.all([loadProject(id), loadProjects()]);
    },
    [loadProject, loadProjects],
  );

  const dismissUpload = useCallback((id: string) => setUploads((u) => u.filter((x) => x.id !== id)), []);

  const refreshPeople = useCallback(async (id: number) => {
    const people = await api.participants(id);
    setSnap((s) => (s && s.pid === id ? { ...s, people } : s));
  }, []);

  const setMe = useCallback(
    async (participantId: number) => {
      const id = pidRef.current;
      if (id === null) return;
      await api.updateParticipant(id, participantId, { is_me: true });
      await refreshPeople(id);
    },
    [refreshPeople],
  );

  const setRoastOptOut = useCallback(
    async (participantId: number, optOut: boolean) => {
      const id = pidRef.current;
      if (id === null) return;
      await api.updateParticipant(id, participantId, { roast_opt_out: optOut });
      await refreshPeople(id);
    },
    [refreshPeople],
  );

  const current = snap && snap.pid === pid ? snap : null;

  const value = useMemo<Studio>(
    () => ({
      status,
      error,
      projects,
      pid,
      project: current?.project ?? null,
      missing: current?.missing ?? false,
      people: current?.people ?? [],
      jobs: current?.jobs ?? [],
      uploads,
      retry,
      createProject,
      removeProject,
      removeChat,
      addFiles,
      startWithFiles,
      renameProject,
      dismissUpload,
      setMe,
      setRoastOptOut,
    }),
    [status, error, projects, pid, current, uploads, retry, createProject, removeProject, removeChat, addFiles,
      startWithFiles, renameProject, dismissUpload, setMe, setRoastOptOut],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
