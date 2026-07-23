"use client";
import { useState } from "react";
import { useOpsStore } from "@/store/opsStore";
import { streamSSE } from "@/lib/api";
import StatusPipeline from "@/components/shared/StatusPipeline";
import OpsViewWrapper from "@/components/shared/OpsViewWrapper";
import type { StatusStep } from "@/lib/types";

// ── Rendered group brief card ─────────────────────────────────────────────────

function SectionLabel({ children, color }: { children: React.ReactNode; color?: string }) {
  return (
    <div style={{
      fontWeight: 600,
      fontSize: "0.7rem",
      textTransform: "uppercase",
      letterSpacing: "0.07em",
      color: color ?? "rgba(230,32,32,0.65)",
      marginBottom: "0.4rem",
    }}>
      {children}
    </div>
  );
}

function GroupBriefCard({ brief }: { brief: Record<string, unknown> }) {
  const organiser      = brief.organiser as string | undefined;
  const eventDate      = brief.event_date as string | undefined;
  const attendeeCount  = brief.attendee_count as number | undefined;
  const summary        = brief.summary as string | undefined;
  const pastFailures   = (brief.past_failures as Array<{ event: string; issue: string; severity: string }> | undefined) ?? [];
  const accessNeeds    = (brief.accessibility_needs as Array<{ need: string; source?: string }> | undefined) ?? [];
  const privacyFlags   = (brief.privacy_flags as string[] | undefined) ?? [];
  const facilActions   = (brief.facilities_actions as string[] | undefined) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.1rem" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "0.4rem" }}>
        <div style={{ fontWeight: 700, fontSize: "1.05rem", color: "#1A1A1A" }}>
          {organiser ?? "Group Event"}
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "baseline" }}>
          {eventDate && (
            <span style={{ fontSize: "0.78rem", color: "rgba(26,26,26,0.45)", fontFamily: "monospace" }}>
              📅 {eventDate}
            </span>
          )}
          {attendeeCount != null && (
            <span style={{ fontSize: "0.78rem", color: "rgba(26,26,26,0.45)" }}>
              {attendeeCount} attendees
            </span>
          )}
        </div>
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

      {/* Accessibility needs — shown first so facilities team act on them */}
      {accessNeeds.length > 0 && (
        <div>
          <SectionLabel color="#dc2626">Accessibility &amp; Safety Needs</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {accessNeeds.map((n, i) => (
              <div key={i} style={{
                background: "rgba(239,68,68,0.05)",
                border: "1px solid rgba(239,68,68,0.2)",
                borderRadius: 8,
                padding: "0.55rem 0.85rem",
                display: "flex",
                flexDirection: "column",
                gap: "0.15rem",
              }}>
                <span style={{ fontSize: "0.83rem", color: "rgba(26,26,26,0.8)", lineHeight: 1.5 }}>{n.need}</span>
                {n.source && (
                  <span style={{ fontSize: "0.72rem", color: "rgba(26,26,26,0.4)", fontStyle: "italic" }}>source: {n.source}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Privacy flags */}
      {privacyFlags.length > 0 && (
        <div>
          <SectionLabel color="#b45309">Privacy Flags</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            {privacyFlags.map((f, i) => (
              <div key={i} style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.5rem",
                background: "rgba(234,179,8,0.05)",
                border: "1px solid rgba(234,179,8,0.22)",
                borderRadius: 8,
                padding: "0.5rem 0.85rem",
                fontSize: "0.83rem",
                color: "rgba(26,26,26,0.75)",
                lineHeight: 1.5,
              }}>
                <span style={{ flexShrink: 0, marginTop: "0.05rem" }}>⚠</span>
                <span>{f}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Past failures */}
      {pastFailures.length > 0 && (
        <div>
          <SectionLabel>Past Failures</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            {pastFailures.map((f, i) => {
              const isHigh = f.severity === "high" || f.severity === "critical";
              return (
                <div key={i} style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.5rem",
                  fontSize: "0.83rem",
                  color: "rgba(26,26,26,0.75)",
                  lineHeight: 1.55,
                  padding: "0.45rem 0.75rem",
                  background: isHigh ? "rgba(239,68,68,0.04)" : "transparent",
                  border: isHigh ? "1px solid rgba(239,68,68,0.12)" : "1px solid rgba(230,32,32,0.08)",
                  borderRadius: 8,
                }}>
                  <span style={{ color: "rgba(230,32,32,0.35)", flexShrink: 0, marginTop: "0.1rem" }}>–</span>
                  <span style={{ flex: 1 }}>{f.issue || f.event}</span>
                  {f.severity && <span className={`severity-badge severity-${f.severity}`} style={{ flexShrink: 0 }}>{f.severity}</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Facilities actions */}
      {facilActions.length > 0 && (
        <div style={{
          background: "rgba(22,163,74,0.04)",
          border: "1px solid rgba(22,163,74,0.18)",
          borderRadius: 10,
          padding: "0.85rem 1.1rem",
        }}>
          <SectionLabel color="#16a34a">Facilities Actions</SectionLabel>
          <ol style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {facilActions.map((a, i) => (
              <li key={i} style={{ fontSize: "0.84rem", color: "rgba(26,26,26,0.78)", lineHeight: 1.55 }}>{a}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function GroupBriefView() {
  const store = useOpsStore();
  const { guestUsers, groupBriefs } = store;

  const [organiserId, setOrganiserId] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [attendeeCount, setAttendeeCount] = useState(30);
  const [submitting, setSubmitting] = useState(false);
  const [steps, setSteps] = useState<StatusStep[]>([]);
  const [totalMs, setTotalMs] = useState<number | undefined>();
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [resultOpen, setResultOpen] = useState(true);
  const [error, setError] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [expandedBrief, setExpandedBrief] = useState<number | null>(null);

  function handleGenerate() {
    if (!organiserId || !eventDate) { setError("Please select an organiser and event date."); return; }
    if (eventDate < new Date().toISOString().split("T")[0]) { setError("Event date cannot be in the past."); return; }
    setError(""); setSubmitting(true); setSteps([]); setResult(null); setTotalMs(undefined); setResultOpen(true);
    const organiser = guestUsers.find((g) => g.user_id === organiserId);
    streamSSE(
      "/ops/group-brief/stream",
      { organiser_id: organiserId, event_date: eventDate, attendee_count: attendeeCount },
      (type, data) => {
        if (type === "status") setSteps((p) => [...p, data as unknown as StatusStep]);
        else if (type === "status_complete") {
          const d = data as { steps: StatusStep[]; total_ms: number };
          setSteps(d.steps); setTotalMs(d.total_ms);
        } else if (type === "response") {
          const d = data as Record<string, unknown>;
          setResult(d);
          store.addGroupBrief({ ...d, _organiser_name: organiser?.name, _event_date: eventDate, _attendee_count: attendeeCount });
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
        <h2 style={{ margin: "0 0 0.4rem", fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>Group Event Pre-Brief</h2>
        <div style={{ display: "flex", gap: "0.4rem" }}>
          <span className="memory-pill">Group organiser memory</span>
          <span className="memory-pill">Saved to role_events memory</span>
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
          <label className="form-label">Event Organiser</label>
          <select className="form-select" value={organiserId} onChange={(e) => setOrganiserId(e.target.value)}>
            <option value="">Select organiser…</option>
            {guestUsers.map((g) => (
              <option key={g.user_id} value={g.user_id}>{g.name}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div>
            <label className="form-label">Event date</label>
            <input
              type="date"
              className="form-input"
              value={eventDate}
              min={new Date().toISOString().split("T")[0]}
              onChange={(e) => setEventDate(e.target.value)}
            />
          </div>
          <div>
            <label className="form-label">Attendee count</label>
            <input
              type="number"
              className="form-input"
              value={attendeeCount}
              min={1}
              max={500}
              onChange={(e) => setAttendeeCount(Number(e.target.value))}
            />
          </div>
        </div>

        {error && (
          <div style={{ background: "rgba(220,38,38,0.05)", border: "1px solid rgba(220,38,38,0.2)", borderRadius: 6, padding: "0.55rem 0.8rem", fontSize: "0.82rem", color: "#dc2626" }}>
            {error}
          </div>
        )}

        <button className="btn-primary" style={{ alignSelf: "flex-start" }} onClick={handleGenerate} disabled={submitting}>
          {submitting ? "Generating…" : "Generate group brief"}
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
            {(result as { write_ok?: boolean }).write_ok ? (
              <span style={{ fontSize: "0.82rem", color: "#16a34a", fontWeight: 600 }}>✓ Written to role_events memory</span>
            ) : (
              <span style={{ fontSize: "0.82rem", color: "#16a34a", fontWeight: 600 }}>✓ Brief ready</span>
            )}
            <button
              onClick={() => setResultOpen((v) => !v)}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: "0.8rem", color: "rgba(26,26,26,0.45)", display: "flex", alignItems: "center", gap: "0.3rem" }}
            >
              Group brief {resultOpen ? "▲" : "▼"}
            </button>
          </div>
          {resultOpen && (
            <div style={{ padding: "1.5rem 1.75rem" }}>
              <GroupBriefCard brief={(result.brief ?? result) as Record<string, unknown>} />
            </div>
          )}
        </div>
      )}

      {/* Session history */}
      {groupBriefs.length > 0 && (
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
            Session history ({groupBriefs.length} this session)
          </button>

          {historyOpen && (
            <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {(groupBriefs as Record<string, unknown>[]).map((b, i) => {
                const organiserName  = b._organiser_name as string | undefined;
                const date           = b._event_date as string | undefined;
                const count          = b._attendee_count as number | undefined;
                const brief          = (b.brief ?? b) as Record<string, unknown>;
                const summary        = brief.summary as string | undefined;
                const isExpanded     = expandedBrief === i;
                return (
                  <div key={i} style={{
                    background: "rgba(255,255,255,0.65)",
                    border: "1px solid rgba(230,32,32,0.1)",
                    borderRadius: 10,
                    overflow: "hidden",
                  }}>
                    <div
                      style={{ padding: "0.7rem 1rem", display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}
                      onClick={() => setExpandedBrief(isExpanded ? null : i)}
                    >
                      <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "#1A1A1A" }}>{organiserName ?? "Unknown organiser"}</span>
                      {date && <span style={{ fontSize: "0.75rem", color: "rgba(26,26,26,0.45)" }}>{date}</span>}
                      {count != null && <span style={{ fontSize: "0.72rem", color: "rgba(26,26,26,0.4)" }}>{count} attendees</span>}
                      <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "rgba(26,26,26,0.35)" }}>{isExpanded ? "▲" : "▼"}</span>
                    </div>
                    {summary && !isExpanded && (
                      <div style={{ padding: "0 1rem 0.65rem", fontSize: "0.78rem", color: "rgba(26,26,26,0.5)", fontStyle: "italic", lineHeight: 1.5 }}>
                        {summary}
                      </div>
                    )}
                    {isExpanded && (
                      <div style={{ borderTop: "1px solid rgba(230,32,32,0.07)", padding: "1.25rem 1.5rem" }}>
                        <GroupBriefCard brief={brief} />
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
