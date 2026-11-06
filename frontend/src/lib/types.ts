// Shapes returned by the AddaMind API (backend/chatintel/api.py).

export interface Project {
  id: number;
  name: string;
  created_at: string;
  chat_count: number;
}

export interface Chat {
  id: number;
  project_id: number;
  title: string;
  kind: "group" | "direct";
  source_format: "android" | "ios";
  status: "processing" | "ready" | "failed";
  created_at: string;
  message_count: number;
  member_count: number;
  media_count: number;
  first_ts: string | null;
  last_ts: string | null;
}

export interface ProjectDetail extends Project {
  chats: Chat[];
}

export type JobStage = "queued" | "parse" | "media" | "index" | "memory" | "personas" | "done";

export interface Job {
  id: number;
  chat_id: number | null;
  filename: string;
  status: "queued" | "running" | "done" | "failed";
  stage: JobStage;
  done: number;
  total: number;
  error: string | null;
  info: JobInfo;
  created_at: string;
  updated_at: string;
}

/** What each stage reports as it finishes. Every field is optional: later stages add to earlier ones. */
export interface JobInfo {
  title?: string;
  kind?: "group" | "direct";
  created?: boolean;
  messages?: number;
  inserted?: number;
  skipped?: number;
  months?: string[];
  media_saved?: number;
  media_missing?: number;
  media_done?: number;
  media_failed?: number;
  media_skipped?: number;
  media_pending?: number;
  passages?: number;
  embedded?: number;
  months_summarised?: number;
  months_failed?: string[];
  events?: number;
  inside_jokes?: number;
  personas?: number;
  personas_failed?: number;
  memory?: string;
}

export interface Participant {
  id: number;
  name: string;
  is_me: boolean;
  roast_opt_out: boolean;
  masked: boolean;
  message_count: number;
  chat_ids: number[];
}

export interface PersonStats {
  id: number;
  name: string;
  is_me: boolean;
  messages: number;
  share: number;
  conversation_starts: number;
  median_reply_s: number | null;
  night_messages: number;
  avg_text_length: number | null;
  emoji: number;
  media: Record<string, number>;
  longest_silence: { days: number; from: string | null; to: string | null; until_end: boolean };
}

export interface Award {
  award: "night_owl" | "ghost" | "speed_replier" | "essayist" | "hype_machine" | "lurker";
  title: string;
  participant_id: number;
  name: string;
  value: number;
  unit: string;
  message_ids: number[];
  rule: string;
}

/** GET /projects/{pid}/chats/{cid}/stats: exact counts from SQL. */
export interface ChatStats {
  scope: { project_id: number; chat_id: number | null; chat_title: string | null };
  totals: {
    messages: number;
    participants: number;
    active_participants: number;
    conversations: number;
    first: string | null;
    last: string | null;
    active_days: number;
    media: Record<string, number>;
  };
  activity: { by_hour: number[]; by_weekday: number[]; busiest_day: { date: string; messages: number } | null };
  highlights: {
    top_talker: { participant_id: number; name: string; messages: number } | null;
    conversation_starter: { participant_id: number; name: string; starts: number } | null;
    voice_note_king: { participant_id: number; name: string; voice_notes: number } | null;
    power_couple: { participant_ids: number[]; names: string[]; interactions: number } | null;
  };
  top_emoji: [string, number][];
  participants: PersonStats[];
  awards: Award[];
}

export interface MemoryEvent {
  title: string;
  detail: string;
  people: string[];
  message_ids: number[];
  date: string;
  month: string;
}

export interface InsideJoke {
  phrase: string;
  meaning: string;
  started_by: string;
  started_by_id: number;
  first_message_id: number;
  first_date: string;
  uses: number;
  people: number;
  example_ids: number[];
}

/** GET /projects/{pid}/chats/{cid}/memory */
export interface ChatMemory {
  chat_id: number;
  months: number;
  timeline: MemoryEvent[];
  topics: { topic: string; months: string[] }[];
  mood: { month: string; mood: number; reason: string; messages: number; message_ids: number[] }[];
  inside_jokes: InsideJoke[];
  dynamics: {
    overview: string;
    patterns: string[];
    roles: { name: string; role: string }[];
    relationships: { people: string[]; description: string; message_ids: number[] }[];
  } | null;
}

/** GET /projects/{pid}/chats/{cid}/graph */
export interface ReplyGraph {
  nodes: { id: number; name: string; is_me: boolean; messages: number }[];
  edges: { source: number; target: number; replies: number; mentions: number; weight: number }[];
  power_couple: { participant_ids: number[]; interactions: number } | null;
}

export interface Persona {
  participant_id: number;
  name: string;
  summary: string;
  communication_style: string;
  interests: string[];
  humour: string;
  group_role: string;
  catchphrases: { phrase: string; uses: number }[];
  example_message_ids: number[];
}

export interface Health {
  status: string;
  models_available: number;
}
