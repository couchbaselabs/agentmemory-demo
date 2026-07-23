"use client";
import { useState } from "react";
import { useOpsStore } from "@/store/opsStore";
import { streamSSE } from "@/lib/api";
import StatusPipeline from "@/components/shared/StatusPipeline";
import OpsViewWrapper from "@/components/shared/OpsViewWrapper";
import type { StatusStep } from "@/lib/types";


export default function AllergyView() {
  const store = useOpsStore();
  const { guestUsers, flags } = store;

  const [guestId, setGuestId] = useState("");
  const triggerType = "food_order";
  const [payload, setPayload] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [steps, setSteps] = useState<StatusStep[]>([]);
  const [totalMs, setTotalMs] = useState<number | undefined>();
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  function handleSubmit() {
    if (!guestId || !payload.trim()) { setError("Please select a guest and enter a payload."); return; }
    setError(""); setSubmitting(true); setSteps([]); setResult(null); setTotalMs(undefined); setEvidenceOpen(false);
    const guest = guestUsers.find((g) => g.user_id === guestId);
    streamSSE(
      "/ops/flag/stream",
      { guest_id: guestId, trigger_type: triggerType, trigger_payload: payload },
      (type, data) => {
        if (type === "status") setSteps((p) => [...p, data as unknown as StatusStep]);
        else if (type === "status_complete") {
          const d = data as { steps: StatusStep[]; total_ms: number };
          setSteps(d.steps); setTotalMs(d.total_ms);
        } else if (type === "response") {
          const d = data as Record<string, unknown>;
          setResult(d);
          store.addFlag({ ...d, _guest_name: guest?.name, _guest_id: guestId });
        } else if (type === "error") {
          setError((data as { message: string }).message);
        }
      },
      () => setSubmitting(false),
      (err) => { setError(err); setSubmitting(false); },
    );
  }

  const flag = result?.flag as Record<string, unknown> | undefined;
  const severity = flag?.severity as string | undefined;
  const isAlert = severity === "high" || severity === "critical";

  return (
    <OpsViewWrapper>
      <div style={{ borderBottom: "1px solid rgba(230,32,32,0.1)", paddingBottom: "1rem" }}>
        <h2 style={{ margin: "0 0 0.4rem", fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>Food Allergen Check</h2>
        <div style={{ display: "flex", gap: "0.4rem" }}>
          <span className="memory-pill">Food orders only</span>
          <span className="memory-pill">Saved to Front Desk memory</span>
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
          <label className="form-label">Order / booking details</label>
          <textarea
            className="form-textarea"
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            rows={5}
            placeholder="Describe what the guest is ordering or booking. The LLM will cross-check against their known allergies and preferences…"
          />
        </div>

        {error && (
          <div style={{ background: "rgba(220,38,38,0.05)", border: "1px solid rgba(220,38,38,0.2)", borderRadius: 6, padding: "0.55rem 0.8rem", fontSize: "0.82rem", color: "#dc2626" }}>
            {error}
          </div>
        )}

        <button className="btn-primary" style={{ alignSelf: "flex-start" }} onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Checking…" : "Check for safety flags"}
        </button>

        {steps.length > 0 && (
          <div style={{ borderTop: "1px solid rgba(230,32,32,0.08)", paddingTop: "0.9rem" }}>
            <StatusPipeline steps={steps} totalMs={totalMs} />
          </div>
        )}
      </div>

      {/* Result card */}
      {flag && (
        <div style={{
          background: isAlert ? "rgba(239,68,68,0.05)" : "rgba(22,163,74,0.05)",
          border: `1px solid ${isAlert ? "rgba(239,68,68,0.2)" : "rgba(22,163,74,0.2)"}`,
          borderRadius: 14,
          padding: "1.75rem 2rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.85rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontWeight: 700, fontSize: "1rem", color: isAlert ? "#dc2626" : "#16a34a" }}>
              {isAlert ? "⚠️ Safety Flag Raised" : "✓ No conflicts detected"}
            </div>
            {severity && <span className={`severity-badge severity-${severity}`}>{severity}</span>}
          </div>
          {flag.conflict_summary != null && String(flag.conflict_summary) && (
            <div style={{ fontSize: "0.85rem", color: "rgba(26,26,26,0.7)", lineHeight: 1.65 }}>
              {String(flag.conflict_summary)}
            </div>
          )}
          {flag.recommended_action != null && (
            <div style={{ fontSize: "0.83rem", background: isAlert ? "rgba(239,68,68,0.07)" : "rgba(22,163,74,0.07)", borderRadius: 8, padding: "0.65rem 0.85rem" }}>
              <strong>Recommended action:</strong> {String(flag.recommended_action)}
            </div>
          )}
          {(flag.evidence != null || flag.citation != null) && (() => {
            const citation = flag.citation ? String(flag.citation) : "";
            const blockId = citation.replace(/^\[block:?/, "").replace(/\]$/, "").trim();
            const evidence = flag.evidence ? String(flag.evidence) : "";
            return (
              <div style={{ borderRadius: 8, border: "1px solid rgba(26,26,26,0.1)", overflow: "hidden" }}>
                <button
                  onClick={() => setEvidenceOpen((v) => !v)}
                  style={{
                    width: "100%", background: "rgba(26,26,26,0.03)", border: "none", cursor: "pointer",
                    padding: "0.55rem 0.85rem", display: "flex", alignItems: "center", justifyContent: "space-between",
                    fontSize: "0.78rem", color: "rgba(26,26,26,0.6)", textAlign: "left",
                  }}
                >
                  <span>
                    {evidence ? evidence.slice(0, 60) + (evidence.length > 60 ? "…" : "") : "No evidence"}
                    {blockId && <span style={{ marginLeft: "0.5rem", fontFamily: "monospace", fontSize: "0.72rem", color: "rgba(26,26,26,0.35)" }}>· block:{blockId}</span>}
                  </span>
                  <span style={{ flexShrink: 0, marginLeft: "0.5rem" }}>{evidenceOpen ? "▲" : "▼"}</span>
                </button>
                {evidenceOpen && (
                  <div style={{ padding: "0.65rem 0.85rem", fontSize: "0.79rem", fontStyle: "italic", color: "rgba(26,26,26,0.55)", lineHeight: 1.6, borderTop: "1px solid rgba(26,26,26,0.08)" }}>
                    {evidence}
                    {blockId && (
                      <div style={{ marginTop: "0.4rem", fontStyle: "normal", fontFamily: "monospace", fontSize: "0.72rem", color: "rgba(26,26,26,0.3)" }}>
                        block:{blockId}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {/* Session history toggle */}
      {flags.length > 0 && (
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
            Session history ({flags.length} this session)
          </button>

          {historyOpen && (
            <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {(flags as Record<string, unknown>[]).map((f, i) => {
                const inner = (f.flag ?? f) as Record<string, unknown>;
                const sev = inner.severity as string | undefined;
                const isHigh = sev === "high" || sev === "critical";
                const storedName = (f as Record<string, unknown>)._guest_name as string | undefined;
                const storedId = (f as Record<string, unknown>)._guest_id as string | undefined;
                const lookedUp = storedId ? guestUsers.find((g) => g.user_id === storedId)?.name : undefined;
                const guestName = storedName ?? lookedUp ?? storedId ?? "Unknown guest";
                return (
                  <div key={i} style={{
                    background: isHigh ? "rgba(239,68,68,0.04)" : "rgba(22,163,74,0.04)",
                    border: `1px solid ${isHigh ? "rgba(239,68,68,0.15)" : "rgba(22,163,74,0.15)"}`,
                    borderRadius: 10,
                    padding: "0.7rem 1rem",
                    fontSize: "0.82rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.25rem",
                  }}>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, color: "#1A1A1A", fontSize: "0.8rem" }}>{guestName}</span>
                      {sev && <span className={`severity-badge severity-${sev}`}>{sev}</span>}
                      <span style={{ color: "rgba(26,26,26,0.55)", flex: 1 }}>{String(inner.conflict_summary ?? inner.summary ?? "No summary")}</span>
                    </div>
                    {(inner.recommended_action as string | undefined) && (
                      <div style={{ color: "rgba(26,26,26,0.4)", fontSize: "0.76rem", paddingLeft: "0.1rem" }}>→ {String(inner.recommended_action)}</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </OpsViewWrapper>
  );
}
