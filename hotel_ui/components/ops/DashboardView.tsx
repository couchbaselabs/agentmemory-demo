"use client";
import { useState } from "react";
import { useOpsStore } from "@/store/opsStore";
import OpsViewWrapper from "@/components/shared/OpsViewWrapper";

export default function DashboardView() {
  const store = useOpsStore();
  const { activeRole, guestUsers, flags, briefings } = store;
  const [flagsOpen, setFlagsOpen] = useState(false);

  const briefingReadyCount = Object.keys(briefings).length;

  return (
    <OpsViewWrapper>
      <div style={{ borderBottom: "1px solid rgba(230,32,32,0.1)", paddingBottom: "1rem" }}>
        <h2 style={{ margin: "0 0 0.15rem", fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>Dashboard</h2>
        <div style={{ fontSize: "0.82rem", color: "rgba(230,32,32,0.55)", fontWeight: 500, letterSpacing: "0.03em", textTransform: "uppercase" }}>{activeRole?.name}</div>
      </div>

      {/* KPI grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1rem" }}>
        <div className="kpi-card">
          <div className="kpi-value">{guestUsers.length}</div>
          <div className="kpi-label">Guests on file</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-value">{briefingReadyCount}</div>
          <div className="kpi-label">Briefings ready this session</div>
        </div>
      </div>

      {/* Guests in memory */}
      <div>
        <div style={{ fontWeight: 700, fontSize: "0.95rem", marginBottom: "0.75rem" }}>Guests in memory store</div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {guestUsers.length === 0 ? (
            <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>No guests loaded.</div>
          ) : (
            guestUsers.map((g) => {
              const hasBriefing = !!briefings[g.user_id];
              return (
                <div key={g.user_id} className="list-item" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 500 }}>{g.name}</span>
                  <span style={{ fontSize: "0.72rem", color: hasBriefing ? "#16a34a" : "rgba(26,26,26,0.35)" }}>
                    {hasBriefing ? "✓ Briefing ready" : "No briefing yet"}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Recent flags */}
      {flags.length > 0 && (
        <div className="expander">
          <div className="expander-header" onClick={() => setFlagsOpen(!flagsOpen)}>
            <span>Food allergen alerts this session ({flags.length})</span>
            <span>{flagsOpen ? "▲" : "▼"}</span>
          </div>
          {flagsOpen && (
            <div className="expander-body" style={{ display: "flex", flexDirection: "column", gap: "0.5rem", padding: "0.75rem 1rem" }}>
              {(flags as Record<string, unknown>[]).slice(0, 5).map((f, i) => {
                const inner = (f.flag ?? f) as Record<string, unknown>;
                const sev = inner.severity as string | undefined;
                const isHigh = sev === "high" || sev === "critical";
                const guestName = (f._guest_name ?? f._guest_id ?? "Unknown guest") as string;
                const summary = inner.conflict_summary as string | undefined;
                const action = inner.recommended_action as string | undefined;
                return (
                  <div key={i} style={{
                    background: isHigh ? "rgba(239,68,68,0.05)" : "rgba(22,163,74,0.05)",
                    border: `1px solid ${isHigh ? "rgba(239,68,68,0.18)" : "rgba(22,163,74,0.18)"}`,
                    borderRadius: 10,
                    padding: "0.7rem 1rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.25rem",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "#1A1A1A" }}>{guestName}</span>
                      {sev && <span className={`severity-badge severity-${sev}`}>{sev}</span>}
                    </div>
                    {summary && <div style={{ fontSize: "0.8rem", color: "rgba(26,26,26,0.7)", lineHeight: 1.5 }}>{summary}</div>}
                    {action && <div style={{ fontSize: "0.76rem", color: "rgba(26,26,26,0.45)", fontStyle: "italic" }}>→ {action}</div>}
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
