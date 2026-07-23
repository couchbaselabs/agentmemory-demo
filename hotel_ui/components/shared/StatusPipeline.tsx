"use client";
import { useState } from "react";
import type { StatusStep } from "@/lib/types";

const MEMORY_STEPS = new Set(["Memory search", "Memory write"]);

interface Props {
  steps: StatusStep[];
  totalMs?: number | null;
}

function QueryRewriterRow({ step }: { step: StatusStep }) {
  const [open, setOpen] = useState(false);
  const lineClass = step.state === "done" ? "done" : step.state === "running" ? "active" : "";
  const dotClass  = step.state === "done" ? "done" : step.state === "running" ? "running" : "pending";
  const hasQueries = step.queries && step.queries.length > 0;

  return (
    <div>
      <div className={`status-line ${lineClass}`} style={{ justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className={`status-dot ${dotClass}`} />
          <span>{step.step}</span>
          {step.detail && <span style={{ opacity: 0.65 }}>· {step.detail}</span>}
        </div>
        {hasQueries && (
          <button
            onClick={() => setOpen(!open)}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: "0.68rem", color: "rgba(230,32,32,0.6)", padding: "0 0.2rem", fontFamily: "Inter, sans-serif" }}
          >
            {open ? "▲ queries" : "▼ queries"}
          </button>
        )}
      </div>
      {open && hasQueries && (
        <div style={{ marginLeft: "1.1rem", marginTop: "0.2rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          {step.queries!.map((q, i) => (
            <div key={i} style={{ fontSize: "0.73rem", color: "rgba(26,26,26,0.65)", padding: "0.2rem 0.5rem", background: "rgba(230,32,32,0.04)", borderRadius: 4, borderLeft: "2px solid rgba(230,32,32,0.2)" }}>
              {q}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function StatusPipeline({ steps, totalMs }: Props) {
  return (
    <div className="status-pipeline">
      {steps.map((s, i) => {
        if (s.step === "Query rewriter") {
          return <QueryRewriterRow key={i} step={s} />;
        }

        const lineClass = s.state === "done" ? "done" : s.state === "running" ? "active" : "";
        const dotClass  = s.state === "done" ? "done" : s.state === "running" ? "running" : "pending";
        // Subtle green tint on memory steps when done
        const isMemoryDone = s.state === "done" && MEMORY_STEPS.has(s.step);

        return (
          <div
            key={i}
            className={`status-line ${lineClass}`}
            style={isMemoryDone ? { background: "rgba(76,175,130,0.06)", borderRadius: 4, padding: "0.1rem 0.3rem", margin: "0.05rem -0.3rem" } : undefined}
          >
            <div className={`status-dot ${dotClass}`} />
            <span>{s.step}</span>
            {s.detail && <span style={{ opacity: 0.65, marginLeft: "0.25rem" }}>· {s.detail}</span>}
          </div>
        );
      })}
      {totalMs != null && steps.length > 0 && (
        <div className="status-line done" style={{ marginTop: "0.3rem", borderTop: "1px solid rgba(230,32,32,0.08)", paddingTop: "0.3rem" }}>
          <div className="status-dot done" />
          <span>Total · {totalMs}ms</span>
        </div>
      )}
    </div>
  );
}
