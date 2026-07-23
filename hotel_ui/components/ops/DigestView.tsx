"use client";
import { useState } from "react";
import { useOpsStore } from "@/store/opsStore";
import { getDigest } from "@/lib/api";
import OpsViewWrapper from "@/components/shared/OpsViewWrapper";

export default function DigestView() {
  const store = useOpsStore();
  const { digest, digestGeneratedAt } = store;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run(force: boolean) {
    setError(""); setLoading(true);
    try {
      const r = await getDigest(force);
      store.setDigest(r.digest, r.generated_at);
    } catch (e: unknown) {
      setError((e as Error).message || "Failed to generate digest");
    } finally {
      setLoading(false);
    }
  }

  function formatArrayItem(item: unknown): string {
    if (typeof item !== "object" || item === null) return String(item);
    const obj = item as Record<string, unknown>;
    // First key is usually the main label (issue, request, name…)
    const entries = Object.entries(obj);
    if (entries.length === 0) return "";
    const [, primary] = entries[0];
    const rest = entries.slice(1).map(([k, val]) => `${k.replace(/_/g, " ")}: ${val}`).join(" · ");
    return rest ? `${primary}  —  ${rest}` : String(primary);
  }

  function renderDigest(d: Record<string, unknown>) {
    return Object.entries(d).map(([k, v]) => {
      if (typeof v === "object" && v !== null && !Array.isArray(v)) {
        return (
          <div key={k} style={{ marginBottom: "1rem" }}>
            <div style={{ fontWeight: 700, fontSize: "0.88rem", marginBottom: "0.4rem", textTransform: "capitalize", color: "#1A1A1A" }}>
              {k.replace(/_/g, " ")}
            </div>
            <div style={{ paddingLeft: "0.75rem", borderLeft: "2px solid rgba(230,32,32,0.25)" }}>
              {renderDigest(v as Record<string, unknown>)}
            </div>
          </div>
        );
      }
      if (Array.isArray(v)) {
        return (
          <div key={k} style={{ marginBottom: "1rem" }}>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.45rem", textTransform: "capitalize", color: "rgba(26,26,26,0.75)" }}>
              {k.replace(/_/g, " ")}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              {v.map((item, i) => (
                <div key={i} style={{
                  fontSize: "0.82rem",
                  color: "rgba(26,26,26,0.65)",
                  background: "rgba(230,32,32,0.04)",
                  borderRadius: 6,
                  padding: "0.4rem 0.7rem",
                  lineHeight: 1.5,
                }}>
                  {typeof item === "object" ? formatArrayItem(item) : String(item)}
                </div>
              ))}
            </div>
          </div>
        );
      }
      return (
        <div key={k} style={{ marginBottom: "0.5rem", fontSize: "0.84rem", lineHeight: 1.6 }}>
          <strong style={{ textTransform: "capitalize", color: "rgba(26,26,26,0.75)" }}>{k.replace(/_/g, " ")}: </strong>
          <span style={{ color: "rgba(26,26,26,0.6)" }}>{String(v)}</span>
        </div>
      );
    });
  }

  return (
    <OpsViewWrapper>
      <div style={{ borderBottom: "1px solid rgba(230,32,32,0.1)", paddingBottom: "1rem" }}>
        <h2 style={{ margin: "0 0 0.4rem", fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>Monthly Ops Digest</h2>
        <div style={{ display: "flex", gap: "0.4rem" }}>
          <span className="memory-pill">All guests · All sessions</span>
          <span className="memory-pill">Saved to role_gm memory</span>
        </div>
      </div>

      {/* Action card */}
      <div style={{
        background: "rgba(255,255,255,0.7)",
        border: "1px solid rgba(230,32,32,0.12)",
        borderRadius: 14,
        padding: "1.75rem 2rem",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        width: "100%",
      }}>
        {!digest && (
          <p style={{ margin: 0, fontSize: "0.88rem", color: "rgba(26,26,26,0.55)", lineHeight: 1.6 }}>
            Generates a property-wide monthly summary across all guests and sessions — top themes, service recovery patterns, VIP preferences, and group event highlights.
          </p>
        )}

        <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
          <button className="btn-primary" onClick={() => run(false)} disabled={loading}>
            {loading ? "Generating…" : digest ? "Regenerate digest" : "Generate digest"}
          </button>
          {digest && (
            <button className="btn-secondary" onClick={() => run(true)} disabled={loading}>
              Force refresh
            </button>
          )}
          {digestGeneratedAt && (
            <span style={{ fontSize: "0.75rem", color: "rgba(26,26,26,0.4)", marginLeft: "0.25rem" }}>
              Last generated: {new Date(digestGeneratedAt).toLocaleString()}
            </span>
          )}
        </div>

        {error && (
          <div style={{ background: "rgba(220,38,38,0.05)", border: "1px solid rgba(220,38,38,0.2)", borderRadius: 6, padding: "0.55rem 0.8rem", fontSize: "0.82rem", color: "#dc2626" }}>
            {error}
          </div>
        )}

        {digest && (
          <div style={{ borderTop: "1px solid rgba(230,32,32,0.08)", paddingTop: "1.25rem" }}>
            {renderDigest(digest)}
          </div>
        )}
      </div>
    </OpsViewWrapper>
  );
}
