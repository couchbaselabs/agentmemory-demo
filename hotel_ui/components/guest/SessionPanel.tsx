"use client";
import { useGuestStore } from "@/store/guestStore";
import { createSession, listSessions, endSession, getSessionMessages } from "@/lib/api";
import type { ChatMsg } from "@/lib/types";

function stripSpeakerPrefix(content: string): string {
  // Stored turns often begin with "Alice Chen: " or "Hotels Operations - Duty Manager…: "
  // Strip anything up to the first ": " that looks like a name/label (no JSON, no newlines).
  if (!content.includes(": ")) return content;
  const [prefix, ...rest] = content.split(": ");
  if (rest.length && !prefix.startsWith("{") && !prefix.includes("\n") && prefix.length < 80) {
    return rest.join(": ").trim();
  }
  return content;
}

function pairsToMessages(pairs: unknown[]): ChatMsg[] {
  return (pairs as Array<{ role: string; content: string; timestamp: string }>).map((p, i) => ({
    id: `hist-${i}-${p.role}`,
    role: p.role as "user" | "assistant",
    content: stripSpeakerPrefix(p.content),
    timestamp: p.timestamp || "",
    historical: true,
  }));
}

export default function SessionPanel() {
  const store = useGuestStore();
  const { activeUser, allSessions, currentSessionId, isSessionReadonly, endedSessionIds, memoryPolicy, chatMessages } = store;

  async function handleNewChat() {
    if (!activeUser) return;
    try {
      const result = await createSession(activeUser.user_id, memoryPolicy.mode, memoryPolicy.ttlSeconds);
      const updated = await listSessions(activeUser.user_id);
      store.setSessions(updated.sessions);
      store.setCurrentSession(result.session_id, false);
      store.setMessages([]);
    } catch (e) { console.error(e); }
  }

  async function handleEndSession() {
    if (!activeUser || !currentSessionId) return;
    try {
      await endSession(activeUser.user_id, currentSessionId);
      store.addEndedSession(currentSessionId);
      const updated = await listSessions(activeUser.user_id);
      store.setSessions(updated.sessions);
      store.setCurrentSession(null, true);
      store.setMessages([]);
    } catch (e) { console.error(e); }
  }

  async function handleSessionChange(e: React.ChangeEvent<HTMLSelectElement>) {
    if (!activeUser) return;
    const sid = e.target.value;
    const isEnded = endedSessionIds.has(sid);
    store.setCurrentSession(sid, isEnded);
    store.setMessages([]);
    // Load historical messages for this session
    try {
      const r = await getSessionMessages(activeUser.user_id, sid);
      const msgs = pairsToMessages(r.messages as unknown[]);
      store.setMessages(msgs);
    } catch { /* ignore — session may have no messages */ }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div className="panel-section-title">Sessions</div>
      <div style={{ display: "flex", gap: "0.4rem" }}>
        <button className="btn-secondary" style={{ flex: 1, fontSize: "0.78rem", padding: "0.4rem 0.5rem" }} onClick={handleNewChat}>
          + New Chat
        </button>
        <button
          className="btn-secondary"
          style={{ flex: 1, fontSize: "0.78rem", padding: "0.4rem 0.5rem" }}
          onClick={handleEndSession}
          disabled={!currentSessionId || isSessionReadonly || chatMessages.length === 0}
        >
          End Session
        </button>
      </div>
      {allSessions.length > 0 && (
        <select
          className="form-select"
          style={{ fontSize: "0.78rem" }}
          value={currentSessionId ?? ""}
          onChange={handleSessionChange}
        >
          {allSessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
