// ── Personas & users ──────────────────────────────────────────────────────

export interface Persona {
  user_id: string;
  display_name: string;
  full_name: string;
  type: string;
  stays: string;
  desc: string;
  initials: string;
  password: string;
}

export interface GuestUser {
  user_id: string;
  name: string;
  type: string;
  initials: string;
  desc?: string;
  stays?: string;
}

// ── Sessions ──────────────────────────────────────────────────────────────

export interface SessionInfo {
  session_id: string;
  number: number;
  preview: string;
  label: string;
}

// ── Chat messages ─────────────────────────────────────────────────────────

export interface StatusStep {
  step: string;
  state: "running" | "done" | "pending";
  detail?: string;
  queries?: string[]; // populated for "Query rewriter" step when done
}

export interface MemoryRecord {
  block_id: string;
  kind: "chat" | "fact" | "summary" | "context" | "unknown";
  user_content?: string;
  assistant_content?: string;
  text?: string;
  ingested_at?: string;
}

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  statusSteps?: StatusStep[];
  totalMs?: number;
  memoryUpdateMs?: number;
  memoryRecords?: MemoryRecord[];
  historical?: boolean; // loaded from session history, no pipeline/memory UI
}

// ── Profile ───────────────────────────────────────────────────────────────

export interface ProfileOverview {
  visits?: string;
  preferences?: string;
  dislikes?: string;
  complaints?: string;
  empty?: boolean;
}

// ── Memory policy ─────────────────────────────────────────────────────────

export type MemoryMode = "persistent" | "stay" | "anonymous";

export interface MemoryPolicy {
  mode: MemoryMode;
  ttlSeconds: number;
  ttlLabel: string;
}

// ── Ops roles ─────────────────────────────────────────────────────────────

export interface OpsRole {
  name: string;
  tagline: string;
  password: string;
  default_view: string;
  allowed_views: string[];
  can_read_role_memory: string[];
}

// ── Safety items ──────────────────────────────────────────────────────────

export interface SafetyItem {
  guest_id: string;
  guest_name: string;
  kind: string;
  severity: "critical" | "high" | "medium" | "low" | string;
  summary: string;
  evidence?: string;
  snippet?: string;
  full?: string;
}

// ── Call logs ─────────────────────────────────────────────────────────────

export interface CallLog {
  guest_id: string;
  guest_name: string;
  category: string;
  category_label: string;
  note: string;
  logged_by: string;
  logged_at: string;
  classified_category?: string;
  canonical_fact?: string;
}

// ── Briefings ─────────────────────────────────────────────────────────────

export interface BriefingResult {
  guest_id: string;
  briefing: Record<string, unknown>;
  retrieval_ms: number;
  synthesis_ms: number;
  arrival_time: string;
}

// ── SSE event types ───────────────────────────────────────────────────────

export type SSEEventType =
  | "status"
  | "status_complete"
  | "response"
  | "memory_update"
  | "memory_records"
  | "error"
  | "done";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
