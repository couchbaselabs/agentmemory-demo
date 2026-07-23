"use client";
import { useState, useEffect } from "react";
import { useOpsStore } from "@/store/opsStore";
import { getCallNoteCategories, streamSSE } from "@/lib/api";
import StatusPipeline from "@/components/shared/StatusPipeline";
import OpsViewWrapper from "@/components/shared/OpsViewWrapper";
import type { StatusStep } from "@/lib/types";

export default function LogCallView() {
  const store = useOpsStore();
  const { guestUsers, callLogs, activeRole, activeRoleId } = store;

  const [categories, setCategories] = useState<Record<string, string>>({});
  const [guestId, setGuestId] = useState("");
  const [category, setCategory] = useState("complaint");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [steps, setSteps] = useState<StatusStep[]>([]);
  const [totalMs, setTotalMs] = useState<number | undefined>();
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    getCallNoteCategories().then((r) => setCategories(r.categories)).catch(() => {});
  }, []);

  function handleSubmit() {
    if (!guestId || !note.trim()) { setError("Please select a guest and enter a note."); return; }
    setError(""); setSubmitting(true); setSteps([]); setResult(null); setTotalMs(undefined);
    const guest = guestUsers.find((g) => g.user_id === guestId);

    streamSSE(
      "/ops/call-note/stream",
      {
        guest_id: guestId,
        raw_note: note,
        staff_category: category,
        logged_by_role: activeRoleId ?? "role_front_desk",
        logged_by_role_name: activeRole?.name ?? "Front Desk",
      },
      (type, data) => {
        if (type === "status") setSteps((p) => [...p, data as unknown as StatusStep]);
        else if (type === "status_complete") {
          const d = data as { steps: StatusStep[]; total_ms: number };
          setSteps(d.steps); setTotalMs(d.total_ms);
        } else if (type === "response") {
          const d = data as Record<string, unknown>;
          setResult(d);
          store.addCallLog({
            guest_id: guestId,
            guest_name: guest?.name ?? guestId,
            category,
            category_label: categories[category] ?? category,
            note,
            logged_by: activeRole?.name ?? "Staff",
            logged_at: new Date().toLocaleString(),
            classified_category: d.classified_category as string,
            canonical_fact: d.canonical_fact as string,
          });
          setNote("");
        } else if (type === "error") {
          setError((data as { message: string }).message);
        }
      },
      () => setSubmitting(false),
      (err) => { setError(err); setSubmitting(false); },
    );
  }

  return (
    <OpsViewWrapper>
      <div style={{ borderBottom: "1px solid rgba(230,32,32,0.1)", paddingBottom: "1rem" }}>
        <h2 style={{ margin: "0 0 0.4rem", fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>Log Guest Call</h2>
        <div style={{ display: "flex", gap: "0.4rem" }}>
          <span className="memory-pill">Phoned-in or in-person</span>
          <span className="memory-pill">Saved to guest memory</span>
        </div>
      </div>

      {/* Form card */}
      <div style={{
        background: "rgba(255,255,255,0.7)",
        border: "1px solid rgba(230,32,32,0.12)",
        borderRadius: 14,
        padding: "1.75rem 2rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.1rem",
        width: "100%",
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div>
            <label className="form-label">Guest</label>
            <select className="form-select" value={guestId} onChange={(e) => setGuestId(e.target.value)}>
              <option value="">Select guest…</option>
              {guestUsers.map((g) => (
                <option key={g.user_id} value={g.user_id}>{g.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">Category</label>
            <select className="form-select" value={category} onChange={(e) => setCategory(e.target.value)}>
              {Object.entries(categories).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="form-label">What did the guest say?</label>
          <textarea
            className="form-textarea"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={5}
            placeholder="Describe the guest's feedback, complaint, or request…"
          />
        </div>

        {error && (
          <div style={{ background: "rgba(220,38,38,0.05)", border: "1px solid rgba(220,38,38,0.2)", borderRadius: 6, padding: "0.55rem 0.8rem", fontSize: "0.82rem", color: "#dc2626" }}>
            {error}
          </div>
        )}

        <button className="btn-primary" onClick={handleSubmit} disabled={submitting} style={{ alignSelf: "flex-start" }}>
          {submitting ? "Processing…" : "Add to guest memory"}
        </button>

        {steps.length > 0 && (
          <div style={{ borderTop: "1px solid rgba(230,32,32,0.08)", paddingTop: "0.9rem" }}>
            <StatusPipeline steps={steps} totalMs={totalMs} />
          </div>
        )}
      </div>

      {/* Result card */}
      {result && (
        <div style={{
          background: "rgba(22,163,74,0.05)",
          border: "1px solid rgba(22,163,74,0.2)",
          borderRadius: 14,
          padding: "1.25rem 1.75rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.35rem",
        }}>
          <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "#16a34a" }}>✓ Note saved to memory</div>
          <div style={{ fontSize: "0.82rem", color: "rgba(26,26,26,0.65)", lineHeight: 1.6 }}>
            {result.canonical_fact != null && <div><strong>Canonical fact:</strong> {String(result.canonical_fact)}</div>}
            {result.classified_category != null && <div><strong>Classified as:</strong> {String(result.classified_category)}</div>}
          </div>
        </div>
      )}

      {/* Session history toggle */}
      {callLogs.length > 0 && (
        <div>
          <button
            onClick={() => setHistoryOpen((v) => !v)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: "0.82rem",
              color: "rgba(230,32,32,0.6)",
              fontWeight: 600,
              padding: 0,
              display: "flex",
              alignItems: "center",
              gap: "0.35rem",
            }}
          >
            <span>{historyOpen ? "▲" : "▼"}</span>
            Session history ({callLogs.length} this session)
          </button>

          {historyOpen && (
            <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {callLogs.slice(0, 20).map((log, i) => (
                <div key={i} style={{
                  background: "rgba(255,255,255,0.65)",
                  border: "1px solid rgba(230,32,32,0.1)",
                  borderRadius: 10,
                  padding: "0.7rem 1rem",
                  fontSize: "0.82rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.2rem",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600, color: "#1A1A1A", fontSize: "0.8rem" }}>{log.guest_name}</span>
                    <span style={{ fontSize: "0.72rem", background: "rgba(230,32,32,0.07)", color: "rgba(230,32,32,0.8)", padding: "0.15rem 0.5rem", borderRadius: 4, fontWeight: 500 }}>
                      {log.category_label}
                    </span>
                    <span style={{ fontSize: "0.72rem", color: "rgba(26,26,26,0.4)", marginLeft: "auto" }}>{log.logged_at}</span>
                  </div>
                  <div style={{ color: "rgba(26,26,26,0.6)", lineHeight: 1.55 }}>{log.note}</div>
                  {log.canonical_fact && (
                    <div style={{ color: "rgba(26,26,26,0.4)", fontSize: "0.76rem", fontStyle: "italic" }}>→ {log.canonical_fact}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </OpsViewWrapper>
  );
}
