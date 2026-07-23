import type { GuestUser, SessionInfo, ProfileOverview, OpsRole, SafetyItem } from "./types";

// Route all calls through Next.js rewrite (/api/* → http://localhost:8001/*)
// This avoids CORS entirely and works out-of-the-box with no env vars needed.
const BASE = "/api";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────

export async function login(userId: string, password: string, memoryMode = "persistent", ttlSeconds = 0, ttlLabel = "Forever") {
  return req<{ success: boolean; user_id: string; persona: unknown }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password, memory_mode: memoryMode, memory_ttl_seconds: ttlSeconds, memory_ttl_label: ttlLabel }),
  });
}

export async function opsLogin(roleId: string, password: string) {
  return req<{ success: boolean; role_id: string; role: OpsRole }>("/auth/ops-login", {
    method: "POST",
    body: JSON.stringify({ role_id: roleId, password }),
  });
}

// ── Users ─────────────────────────────────────────────────────────────────

export async function listUsers() {
  return req<{ users: GuestUser[] }>("/users");
}

export async function createUser(name: string) {
  return req<{ user_id: string; name: string; created_ms: number; password: string }>("/users", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function deleteUser(userId: string) {
  return req<{ success: boolean; user_id: string }>(`/users/${userId}`, { method: "DELETE" });
}

// ── Sessions ──────────────────────────────────────────────────────────────

export async function listSessions(userId: string) {
  return req<{ sessions: SessionInfo[] }>(`/users/${userId}/sessions`);
}

export async function createSession(userId: string, memoryMode = "persistent", ttlSeconds = 0) {
  return req<{ session_id: string; number: number }>(`/users/${userId}/sessions`, {
    method: "POST",
    body: JSON.stringify({ memory_mode: memoryMode, memory_ttl_seconds: ttlSeconds }),
  });
}

export async function endSession(userId: string, sessionId: string) {
  return req<{ success: boolean }>(`/sessions/${sessionId}/end?user_id=${userId}`, { method: "POST" });
}

export async function getSessionMessages(userId: string, sessionId: string) {
  return req<{ messages: unknown[] }>(`/users/${userId}/sessions/${sessionId}/messages`);
}

// ── Profile ───────────────────────────────────────────────────────────────

export async function getProfile(userId: string) {
  return req<{ profile: ProfileOverview; retrieval_ms: number; synthesis_ms: number }>(`/users/${userId}/profile`);
}

// ── Meta ──────────────────────────────────────────────────────────────────

export async function getRoles() {
  return req<{ roles: Record<string, OpsRole> }>("/meta/roles");
}

export async function getPersonas() {
  return req<{ personas: Record<string, unknown> }>("/meta/personas");
}

export async function getMemoryPresets() {
  return req<{ presets: Record<string, number> }>("/meta/memory-presets");
}

export async function getCallNoteCategories() {
  return req<{ categories: Record<string, string> }>("/ops/call-note-categories");
}

// ── Ops ───────────────────────────────────────────────────────────────────

export async function getOpsGuests() {
  return req<{ guests: GuestUser[] }>("/ops/guests");
}

export async function getSafetyScan(force = false) {
  return req<{ items: SafetyItem[]; scanned_at: string; cached: boolean }>(`/ops/safety-scan?force=${force}`);
}

export async function getDigest(force = false) {
  return req<{ digest: Record<string, unknown>; generated_at: string; cached: boolean; retrieval_ms?: number; synthesis_ms?: number }>(`/ops/digest?force=${force}`);
}

export async function getRoleMemory(roleId: string) {
  return req<{ blocks: unknown[]; role_id: string; count: number }>(`/ops/role-memory/${roleId}`);
}

// ── SSE stream helper ─────────────────────────────────────────────────────

export function streamSSE(
  path: string,
  body: Record<string, unknown>,
  onEvent: (type: string, data: Record<string, unknown>) => void,
  onDone?: () => void,
  onError?: (err: string) => void,
): () => void {
  const ctrl = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        onError?.(`HTTP ${res.status}`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() ?? "";
        for (const chunk of lines) {
          const line = chunk.trim();
          if (!line.startsWith("data: ")) continue;
          try {
            const parsed = JSON.parse(line.slice(6));
            onEvent(parsed.type, parsed.data);
            if (parsed.type === "done") onDone?.();
          } catch { /* ignore malformed */ }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== "AbortError") onError?.(String(e));
    }
  })();

  return () => ctrl.abort();
}
