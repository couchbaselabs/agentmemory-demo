"use client";
import { useState, useEffect } from "react";
import { useOpsStore } from "@/store/opsStore";
import { getRoleMemory } from "@/lib/api";
import OpsViewWrapper from "@/components/shared/OpsViewWrapper";

const ROLE_LABELS: Record<string, string> = {
  role_gm: "General Manager",
  role_front_desk: "Front Desk",
  role_events: "Events Coordinator",
  role_facilities: "Facilities",
};

const ROLE_ICONS: Record<string, string> = {
  role_gm: "🏢",
  role_front_desk: "🛎️",
  role_events: "🎪",
  role_facilities: "🔧",
};

export default function RoleMemoryView() {
  const store = useOpsStore();
  const { activeRole } = store;

  const [blocks, setBlocks] = useState<Record<string, unknown[]>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [openBlocks, setOpenBlocks] = useState<Record<string, boolean>>({});
  const [expandedBlock, setExpandedBlock] = useState<Record<string, boolean>>({});

  const readableRoles = activeRole?.can_read_role_memory ?? [];

  // Auto-load all readable roles when view mounts
  useEffect(() => {
    readableRoles.forEach((roleId) => {
      if (!blocks[roleId]) loadMemory(roleId);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readableRoles.join(",")]);

  async function loadMemory(roleId: string) {
    setLoading((p) => ({ ...p, [roleId]: true }));
    try {
      const r = await getRoleMemory(roleId);
      setBlocks((p) => ({ ...p, [roleId]: r.blocks }));
      setOpenBlocks((p) => ({ ...p, [roleId]: true }));
    } catch { /* ignore */ }
    setLoading((p) => ({ ...p, [roleId]: false }));
  }

  return (
    <OpsViewWrapper>
      <div style={{ borderBottom: "1px solid rgba(230,32,32,0.1)", paddingBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>Role Memory</h2>
          <button
            onClick={() => readableRoles.forEach((r) => loadMemory(r))}
            style={{
              background: "none",
              border: "1px solid rgba(230,32,32,0.25)",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: "0.75rem",
              color: "rgba(230,32,32,0.7)",
              padding: "0.25rem 0.65rem",
              fontWeight: 500,
            }}
          >
            ↻ Refresh all
          </button>
        </div>
        <div style={{ fontSize: "0.82rem", color: "rgba(26,26,26,0.5)", marginTop: "0.3rem" }}>
          Showing memory for roles you can read: {readableRoles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}
        </div>
      </div>

      {readableRoles.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>No role memory accessible for your role.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          {readableRoles.map((roleId) => {
            const roleBlocks = blocks[roleId];
            const isLoading = loading[roleId];
            const isOpen = openBlocks[roleId];

            return (
              <div key={roleId} style={{
                background: "rgba(255,255,255,0.7)",
                border: "1px solid rgba(230,32,32,0.12)",
                borderRadius: 14,
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
              }}>
                {/* Card header */}
                <div style={{
                  padding: "1.1rem 1.4rem",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  borderBottom: isOpen && roleBlocks ? "1px solid rgba(230,32,32,0.08)" : "none",
                  cursor: roleBlocks ? "pointer" : "default",
                }}
                  onClick={() => {
                    if (roleBlocks) setOpenBlocks((p) => ({ ...p, [roleId]: !isOpen }));
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
                    <span style={{ fontSize: "1.3rem" }}>{ROLE_ICONS[roleId] ?? "👤"}</span>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "0.92rem", color: "#1A1A1A" }}>{ROLE_LABELS[roleId] ?? roleId}</div>
                      {roleBlocks && (
                        <div style={{ fontSize: "0.72rem", color: "rgba(26,26,26,0.45)", marginTop: "0.1rem" }}>
                          {roleBlocks.length} memory block{roleBlocks.length !== 1 ? "s" : ""}
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    {!roleBlocks && (
                      <button
                        className="btn-secondary"
                        style={{ fontSize: "0.75rem", padding: "0.3rem 0.75rem" }}
                        onClick={(e) => { e.stopPropagation(); loadMemory(roleId); }}
                        disabled={isLoading}
                      >
                        {isLoading ? "Loading…" : "Load memory"}
                      </button>
                    )}
                    {roleBlocks && (
                      <span style={{ fontSize: "0.65rem", opacity: 0.45 }}>{isOpen ? "▲" : "▼"}</span>
                    )}
                  </div>
                </div>

                {/* Blocks list */}
                {isOpen && roleBlocks && (
                  <div style={{ padding: "0.75rem 1rem", display: "flex", flexDirection: "column", gap: "0.45rem", maxHeight: 420, overflowY: "auto" }}>
                    {roleBlocks.length === 0 ? (
                      <div style={{ fontSize: "0.83rem", color: "var(--text-muted)", padding: "0.5rem 0" }}>No memory blocks found for this role.</div>
                    ) : (
                      roleBlocks.map((b: unknown, i) => {
                        const block = b as Record<string, unknown>;
                        const key = `${roleId}-${i}`;
                        const isExpanded = expandedBlock[key];
                        const text = (block.text || block.user_content || block.assistant_content || "") as string;
                        const snippet = text.length > 100 ? text.slice(0, 100) + "…" : text;
                        const ts = block.ingested_at ? new Date(block.ingested_at as string).toLocaleString() : "";

                        return (
                          <div key={key} style={{ borderRadius: 8, border: "1px solid rgba(230,32,32,0.08)", overflow: "hidden" }}>
                            <div
                              onClick={() => setExpandedBlock((p) => ({ ...p, [key]: !isExpanded }))}
                              style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.75rem", padding: "0.55rem 0.8rem", cursor: "pointer", background: isExpanded ? "rgba(230,32,32,0.03)" : "transparent" }}
                            >
                              <span style={{ fontSize: "0.8rem", color: "rgba(26,26,26,0.7)", lineHeight: 1.5, flex: 1, minWidth: 0 }}>{snippet || "(no text)"}</span>
                              <span style={{ flexShrink: 0, fontSize: "0.65rem", opacity: 0.4 }}>{isExpanded ? "▲" : "▼"}</span>
                            </div>
                            {isExpanded && (
                              <div style={{ padding: "0.5rem 0.8rem 0.65rem", borderTop: "1px solid rgba(230,32,32,0.07)", fontSize: "0.79rem", color: "rgba(26,26,26,0.65)", lineHeight: 1.6 }}>
                                <div>{text}</div>
                                {ts && <div style={{ marginTop: "0.35rem", fontSize: "0.7rem", color: "rgba(26,26,26,0.35)" }}>{ts}</div>}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </OpsViewWrapper>
  );
}
