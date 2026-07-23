"use client";
import { useState } from "react";
import { useOpsStore } from "@/store/opsStore";
import { streamSSE } from "@/lib/api";
import StatusPipeline from "@/components/shared/StatusPipeline";
import OpsViewWrapper from "@/components/shared/OpsViewWrapper";
import type { StatusStep, BriefingResult } from "@/lib/types";

// ── Rendered briefing card ────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontWeight: 600,
      fontSize: "0.7rem",
      textTransform: "uppercase",
      letterSpacing: "0.07em",
      color: "rgba(230,32,32,0.65)",
      marginBottom: "0.4rem",
    }}>
      {children}
    </div>
  );
}

function BriefingCard({ briefing }: { briefing: Record<string, unknown> }) {
  const guest       = briefing.guest as string | undefined;
  const arrival     = briefing.arrival as string | undefined;
  const summary     = briefing.summary as string | undefined;
  const occasion    = briefing.occasion_context as string | undefined;
  const prefs       = (briefing.preferences as string[] | undefined) ?? [];
  const complaints  = (briefing.prior_complaints as Array<{ event: string; severity: string }> | undefined) ?? [];
  const flags       = (briefing.safety_flags as Array<{ person: string; flag: string; severity: string }> | undefined) ?? [];
  const recovery    = (briefing.recovery_actions as string[] | undefined) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.1rem" }}>

      {/* Guest + arrival */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "0.4rem" }}>
        <div style={{ fontWeight: 700, fontSize: "1.05rem", color: "#1A1A1A" }}>{guest}</div>
        {arrival && (
          <div style={{ fontSize: "0.78rem", color: "rgba(26,26,26,0.45)", fontFamily: "monospace" }}>
            ✈ arriving {arrival}
          </div>
        )}
      </div>

      {/* Summary */}
      {summary && (
        <div style={{
          borderLeft: "3px solid rgba(230,32,32,0.35)",
          background: "rgba(230,32,32,0.03)",
          padding: "0.6rem 0.9rem",
          borderRadius: "0 8px 8px 0",
          fontSize: "0.85rem",
          color: "rgba(26,26,26,0.72)",
          fontStyle: "italic",
          lineHeight: 1.65,
        }}>
          {summary}
        </div>
      )}

      {/* Occasion context */}
      {occasion && (
        <div>
          <SectionLabel>Occasion</SectionLabel>
          <div style={{ fontSize: "0.84rem", color: "rgba(26,26,26,0.75)", lineHeight: 1.55 }}>{occasion}</div>
        </div>
      )}

      {/* Safety flags — shown before preferences so staff see them first */}
      {flags.length > 0 && (
        <div>
          <SectionLabel>Safety / Allergy Flags</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {flags.map((f, i) => {
              const isHigh = f.severity === "high" || f.severity === "critical";
              return (
                <div key={i} style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.55rem",
                  flexWrap: "wrap",
                  background: isHigh ? "rgba(239,68,68,0.06)" : "rgba(234,179,8,0.05)",
                  border: `1px solid ${isHigh ? "rgba(239,68,68,0.22)" : "rgba(234,179,8,0.22)"}`,
                  borderRadius: 8,
                  padding: "0.5rem 0.85rem",
                }}>
                  <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "#1A1A1A" }}>{f.person}</span>
                  <span style={{ fontSize: "0.82rem", color: "rgba(26,26,26,0.72)", flex: 1 }}>— {f.flag}</span>
                  <span className={`severity-badge severity-${f.severity}`}>{f.severity}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Preferences */}
      {prefs.length > 0 && (
        <div>
          <SectionLabel>Preferences</SectionLabel>
          <ul style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
            {prefs.map((p, i) => (
              <li key={i} style={{ fontSize: "0.84rem", color: "rgba(26,26,26,0.78)", lineHeight: 1.55 }}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Prior complaints */}
      {complaints.length > 0 && (
        <div>
          <SectionLabel>Prior Complaints</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            {complaints.map((c, i) => (
              <div key={i} style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.5rem",
                fontSize: "0.83rem",
                color: "rgba(26,26,26,0.72)",
                lineHeight: 1.55,
              }}>
                <span style={{ color: "rgba(230,32,32,0.35)", flexShrink: 0, marginTop: "0.1rem" }}>–</span>
                <span style={{ flex: 1 }}>{c.event}</span>
                {c.severity && <span className={`severity-badge severity-${c.severity}`} style={{ flexShrink: 0 }}>{c.severity}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recovery actions */}
      {recovery.length > 0 && (
        <div style={{
          background: "rgba(22,163,74,0.04)",
          border: "1px solid rgba(22,163,74,0.18)",
          borderRadius: 10,
          padding: "0.85rem 1.1rem",
        }}>
          <SectionLabel>Recovery Actions</SectionLabel>
          <ol style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {recovery.map((a, i) => (
              <li key={i} style={{ fontSize: "0.84rem", color: "rgba(26,26,26,0.78)", lineHeight: 1.55 }}>{a}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function BriefingsView() {
  const store = useOpsStore();
  const { guestUsers } = store;

  const [guestId, setGuestId] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("14:00");
  const [submitting, setSubmitting] = useState(false);
  const [steps, setSteps] = useState<StatusStep[]>([]);
  const [totalMs, setTotalMs] = useState<number | undefined>();
  const [result, setResult] = useState<BriefingResult | null>(null);
  const [resultOpen, setResultOpen] = useState(true);
  const [error, setError] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [history, setHistory] = useState<(BriefingResult & { _guest_name: string })[]>([]);

  const today = new Date().toISOString().split("T")[0];

  function handleGenerate() {
    if (!guestId) { setError("Please select a guest."); return; }
    if (!date) { setError("Please select an arrival date."); return; }
    setError(""); setSubmitting(true); setSteps([]); setResult(null); setTotalMs(undefined); setResultOpen(true);
    const arrival = `${date} ${time}`;
    const guest = guestUsers.find((g) => g.user_id === guestId);

    streamSSE(
      "/ops/briefing/stream",
      { guest_id: guestId, arrival_time: arrival },
      (type, data) => {
        if (type === "status") setSteps((p) => [...p, data as unknown as StatusStep]);
        else if (type === "status_complete") {
          const d = data as { steps: StatusStep[]; total_ms: number };
          setSteps(d.steps); setTotalMs(d.total_ms);
        } else if (type === "response") {
          const d = data as { briefing: Record<string, unknown>; retrieval_ms: number; synthesis_ms: number };
          const entry: BriefingResult = { guest_id: guestId, briefing: d.briefing, retrieval_ms: d.retrieval_ms, synthesis_ms: d.synthesis_ms, arrival_time: arrival };
          store.setBriefing(guestId, entry);
          setResult(entry);
          setHistory((p) => [{ ...entry, _guest_name: guest?.name ?? guestId }, ...p]);
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
        <h2 style={{ margin: "0 0 0.4rem", fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>Pre-Arrival Briefings</h2>
        <div style={{ display: "flex", gap: "0.4rem" }}>
          <span className="memory-pill">Guest memory + stay history</span>
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

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div>
            <label className="form-label">Arrival date</label>
            <input
              type="date"
              className="form-input"
              value={date}
              min={today}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
          <div>
            <label className="form-label">Arrival time</label>
            <input
              type="time"
              className="form-input"
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </div>
        </div>

        {error && (
          <div style={{ background: "rgba(220,38,38,0.05)", border: "1px solid rgba(220,38,38,0.2)", borderRadius: 6, padding: "0.55rem 0.8rem", fontSize: "0.82rem", color: "#dc2626" }}>
            {error}
          </div>
        )}

        <button className="btn-primary" style={{ alignSelf: "flex-start" }} onClick={handleGenerate} disabled={submitting}>
          {submitting ? "Generating…" : "Generate briefing"}
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
          background: "rgba(255,255,255,0.7)",
          border: "1px solid rgba(230,32,32,0.12)",
          borderRadius: 14,
          overflow: "hidden",
        }}>
          <div style={{
            padding: "0.85rem 1.5rem",
            borderBottom: "1px solid rgba(230,32,32,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}>
            <span style={{ fontSize: "0.82rem", color: "#16a34a", fontWeight: 600 }}>✓ Briefing ready</span>
            <button
              onClick={() => setResultOpen((v) => !v)}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: "0.8rem", color: "rgba(26,26,26,0.45)", display: "flex", alignItems: "center", gap: "0.3rem" }}
            >
              Briefing {resultOpen ? "▲" : "▼"}
            </button>
          </div>
          {resultOpen && (
            <div style={{ padding: "1.5rem 1.75rem" }}>
              <BriefingCard briefing={result.briefing as Record<string, unknown>} />
            </div>
          )}
        </div>
      )}

      {/* Session history */}
      {history.length > 0 && (
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
            Briefings generated this session ({history.length})
          </button>

          {historyOpen && (
            <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {history.map((b, i) => {
                const isExpanded = expandedIdx === i;
                const summary = (b.briefing as Record<string, unknown>)?.summary as string | undefined;
                return (
                  <div key={i} style={{
                    background: "rgba(255,255,255,0.65)",
                    border: "1px solid rgba(230,32,32,0.1)",
                    borderRadius: 10,
                    overflow: "hidden",
                  }}>
                    <div
                      style={{ padding: "0.7rem 1rem", display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}
                      onClick={() => setExpandedIdx(isExpanded ? null : i)}
                    >
                      <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "#1A1A1A" }}>{b._guest_name}</span>
                      <span style={{ fontSize: "0.75rem", color: "rgba(26,26,26,0.45)" }}>arriving {b.arrival_time}</span>
                      <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "rgba(26,26,26,0.35)" }}>{isExpanded ? "▲" : "▼"}</span>
                    </div>
                    {summary && !isExpanded && (
                      <div style={{ padding: "0 1rem 0.65rem", fontSize: "0.78rem", color: "rgba(26,26,26,0.5)", fontStyle: "italic", lineHeight: 1.5 }}>
                        {summary}
                      </div>
                    )}
                    {isExpanded && (
                      <div style={{ borderTop: "1px solid rgba(230,32,32,0.07)", padding: "1.25rem 1.5rem" }}>
                        <BriefingCard briefing={b.briefing as Record<string, unknown>} />
                      </div>
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
