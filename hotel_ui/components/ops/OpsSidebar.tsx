"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useOpsStore } from "@/store/opsStore";
import { deleteUser } from "@/lib/api";
import DeleteDialog from "@/components/shared/DeleteDialog";
import Toast from "@/components/shared/Toast";

const VIEW_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  "log-call": "Log Guest Call",
  "pre-arrival": "Pre-Arrival Briefings",
  allergy: "Food Allergen Check",
  "group-brief": "Group Event Pre-Brief",
  digest: "Monthly Ops Digest",
  "role-memory": "Role Memory",
  "how-it-works": "How It Works",
};

export default function OpsSidebar() {
  const store = useOpsStore();
  const router = useRouter();
  const { activeRole, activeRoleId, activeView, guestUsers, showDeleteConfirmation, deletionUserId } = store;

  const [selectedGuestId, setSelectedGuestId] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  if (!activeRole) return null;

  function navigate(view: string) {
    store.setActiveView(view);
    router.push(`/ops/${view}`);
  }

  async function handleDeleteGuest() {
    if (!deletionUserId) return;
    const guestName = guestUsers.find((g) => g.user_id === deletionUserId)?.name ?? deletionUserId;
    const t0 = Date.now();
    await deleteUser(deletionUserId).catch(() => {});
    const elapsedMs = Date.now() - t0;
    store.setShowDeleteConfirmation(false);
    store.setDeletionComplete(true);
    const updated = guestUsers.filter((g) => g.user_id !== deletionUserId);
    store.setGuests(updated);
    setSelectedGuestId("");
    setToast(`${guestName} deleted in ${elapsedMs}ms`);
  }

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", height: "100%" }}>
        {/* Active role card */}
        <div className="role-card active" style={{ cursor: "default" }}>
          <div className="role-name">{activeRole.name}</div>
          <div className="role-meta">{activeRole.tagline}</div>
        </div>

        {/* Sign out */}
        <button
          className="btn-secondary"
          style={{ fontSize: "0.78rem" }}
          onClick={() => { store.logout(); router.push("/ops"); }}
        >
          Sign Out
        </button>

        {/* Navigation */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          <div className="panel-section-title" style={{ marginBottom: "0.3rem" }}>Views</div>
          {activeRole.allowed_views.map((v) => (
            <button
              key={v}
              className={`nav-btn ${activeView === v ? "active" : ""}`}
              onClick={() => navigate(v)}
            >
              {activeView === v ? "→ " : "   "}{VIEW_LABELS[v] ?? v}
            </button>
          ))}
        </div>

        {/* Guest management */}
        {guestUsers.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <div className="panel-section-title">Guest Management</div>
            <select
              className="form-select"
              style={{ fontSize: "0.78rem" }}
              value={selectedGuestId}
              onChange={(e) => setSelectedGuestId(e.target.value)}
            >
              <option value="">Select guest…</option>
              {guestUsers.map((g) => (
                <option key={g.user_id} value={g.user_id}>{g.name}</option>
              ))}
            </select>
            <button
              className="btn-danger"
              style={{ fontSize: "0.78rem" }}
              disabled={!selectedGuestId}
              onClick={() => store.setShowDeleteConfirmation(true, selectedGuestId)}
            >
              Delete Guest
            </button>
          </div>
        )}

        {/* DB stats */}
        <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: "0.4rem", padding: "0.5rem 0.5rem 0" }}>
          <button
            className="btn-secondary"
            style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", opacity: 0.65 }}
            onClick={() => router.push("/")}
          >
            ← Home
          </button>
          <div style={{ fontSize: "0.72rem", color: "rgba(26,26,26,0.5)" }}>
            <div>Guests: <strong>{guestUsers.length}</strong> loaded</div>
            <div>Roles: <strong>{Object.keys(store.roles).length}</strong></div>
          </div>
        </div>
      </div>

      {showDeleteConfirmation && deletionUserId && (
        <DeleteDialog
          title="Delete Guest Confirmation"
          description={`This will permanently delete ${guestUsers.find((g) => g.user_id === deletionUserId)?.name ?? deletionUserId} and all associated data. This cannot be undone.`}
          passwordLabel="Enter ops password to confirm deletion:"
          expectedPassword="ops"
          onConfirm={handleDeleteGuest}
          onCancel={() => store.setShowDeleteConfirmation(false)}
        />
      )}
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    </>
  );
}
