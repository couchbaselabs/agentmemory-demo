"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useGuestStore } from "@/store/guestStore";
import { listSessions, createSession, deleteUser, getSessionMessages } from "@/lib/api";
import HotelHeader from "@/components/shared/HotelHeader";
import ResizableLayout from "@/components/shared/ResizableLayout";
import PersonaCard from "@/components/guest/PersonaCard";
import ProfileOverview from "@/components/guest/ProfileOverview";
import SessionPanel from "@/components/guest/SessionPanel";
import ChatArea from "@/components/guest/ChatArea";
import ChatInput from "@/components/guest/ChatInput";
import DeleteDialog from "@/components/shared/DeleteDialog";
import Toast from "@/components/shared/Toast";

export default function GuestChatPage() {
  const store = useGuestStore();
  const router = useRouter();
  const {
    authenticated,
    activeUser,
    currentSessionId,
    isSessionReadonly,
    memoryPolicy,
    showDeleteConfirmation,
  } = store;
  const [toast, setToast] = useState<string | null>(null);

  // Guard: redirect to login if not authenticated
  useEffect(() => {
    if (!authenticated) router.push("/guest");
  }, [authenticated]);

  // Load sessions on mount / user change, then load history of the last session
  useEffect(() => {
    if (!activeUser) return;
    listSessions(activeUser.user_id).then(async (r) => {
      // Auto-create a session for new users who have none
      if (r.sessions.length === 0) {
        try {
          const created = await createSession(activeUser.user_id, memoryPolicy.mode, memoryPolicy.ttlSeconds);
          const updated = await listSessions(activeUser.user_id);
          store.setSessions(updated.sessions);
          store.setCurrentSession(created.session_id, false);
          store.setMessages([]);
        } catch (e) { console.error(e); }
        return;
      }
      store.setSessions(r.sessions);
      if (r.sessions.length > 0) {
        const last = r.sessions[r.sessions.length - 1];
        store.setCurrentSession(last.session_id, false);
        // Load that session's chat history
        try {
          const h = await getSessionMessages(activeUser.user_id, last.session_id);
          const strip = (s: string) => {
            if (!s.includes(": ")) return s;
            const [pre, ...rest] = s.split(": ");
            if (rest.length && !pre.startsWith("{") && !pre.includes("\n") && pre.length < 80) return rest.join(": ").trim();
            return s;
          };
          const msgs = (h.messages as Array<{ role: string; content: string; timestamp: string }>).map((p, i) => ({
            id: `hist-${i}-${p.role}`,
            role: p.role as "user" | "assistant",
            content: strip(p.content),
            timestamp: p.timestamp || "",
            historical: true as const,
          }));
          store.setMessages(msgs);
        } catch { /* no history yet */ }
      }
    }).catch(() => {});
  }, [activeUser?.user_id]);

  async function handleDelete() {
    if (!activeUser) return;
    const name = activeUser.name;
    const t0 = Date.now();
    await deleteUser(activeUser.user_id).catch(() => {});
    const elapsedMs = Date.now() - t0;
    store.setShowDeleteConfirmation(false);
    store.setDeletionComplete(true);
    setToast(`${name} deleted in ${elapsedMs}ms`);
    setTimeout(() => store.logout(), 2000);
  }

  if (!authenticated || !activeUser) return null;

  const initials = activeUser.initials || activeUser.name.slice(0, 2).toUpperCase();
  const policyLabel = memoryPolicy.mode === "persistent"
    ? "Persistent"
    : memoryPolicy.mode === "anonymous"
    ? "Anonymous (GDPR)"
    : `Stay only · expires ${memoryPolicy.ttlLabel}`;

  const policyClass = memoryPolicy.mode === "persistent"
    ? "memory-policy-persistent"
    : memoryPolicy.mode === "anonymous"
    ? "memory-policy-anonymous"
    : "memory-policy-stay";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
      <HotelHeader portalLabel="Guest Concierge" />

      <ResizableLayout
        sidebar={
          <>
            <PersonaCard user={activeUser} active />
            <ProfileOverview />
            <div style={{ display: "flex", gap: "0.4rem" }}>
              <button className="btn-secondary" style={{ flex: 1, fontSize: "0.78rem" }} onClick={() => store.logout()}>Sign Out</button>
              <button className="btn-danger" style={{ flex: 1, fontSize: "0.78rem" }} onClick={() => store.setShowDeleteConfirmation(true)}>Delete User</button>
            </div>
            <SessionPanel />
            <button
              className="btn-secondary"
              style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", opacity: 0.65, marginTop: "auto" }}
              onClick={() => router.push("/")}
            >
              ← Home
            </button>
          </>
        }
        main={
          <>
            {/* Chat header */}
            <div style={{ padding: "0.8rem 1.5rem", background: "rgba(255,248,238,0.9)", borderBottom: "1px solid rgba(230,32,32,0.12)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
                <div className="guest-avatar">{initials}</div>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>{activeUser.name}</span>
                  </div>
                  {currentSessionId && <div style={{ fontSize: "0.72rem", color: "rgba(230,32,32,0.6)", marginTop: "0.1rem" }}>Session: {currentSessionId}</div>}
                </div>
              </div>
              <span className={`memory-policy-badge ${policyClass}`}>Memory: {policyLabel}</span>
            </div>
            {isSessionReadonly && <div className="readonly-banner">Viewing a previous session (read-only). Click <strong>New Chat</strong> to start a new conversation.</div>}
            {!currentSessionId && !isSessionReadonly && <div style={{ padding: "2rem 1.5rem", textAlign: "center", color: "rgba(26,26,26,0.45)", fontSize: "0.88rem" }}>Click <strong>New Chat</strong> in the sidebar to start a conversation.</div>}
            <ChatArea />
            <ChatInput />
          </>
        }
      />

      {/* Delete confirmation dialog */}
      {showDeleteConfirmation && (
        <DeleteDialog
          title="Delete User Confirmation"
          description={`This will permanently delete ${activeUser.name}'s account and all associated data. This cannot be undone.`}
          expectedPassword="123"
          onConfirm={handleDelete}
          onCancel={() => store.setShowDeleteConfirmation(false)}
        />
      )}
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    </div>
  );
}
