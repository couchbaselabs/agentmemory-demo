import OpsViewWrapper from "@/components/shared/OpsViewWrapper";

export default function HowItWorksView() {
  const sections = [
    {
      title: "Guest Memory Store",
      icon: "🧠",
      body: "Every guest interaction — chat turns, call notes, service requests, complaints, preferences — is stored as a structured memory block in Couchbase. Memories persist across sessions and are retrieved via semantic search at query time.",
    },
    {
      title: "Concierge Agent",
      icon: "💬",
      body: "When a guest sends a message, a query rewriter expands it into 3+ refined queries. Each query searches Couchbase Agent Memory across all sessions. The LLM then crafts a personalised reply grounded in retrieved context, and the turn is written back to memory.",
    },
    {
      title: "Pre-Arrival Briefings",
      icon: "📋",
      body: "Front desk staff trigger a briefing for an arriving guest. The briefing agent fans out across 8+ memory search queries to surface preferences, complaints, dietary needs, and past service recovery — then synthesises a structured handover note.",
    },
    {
      title: "Allergy & Safety Flagging",
      icon: "⚠️",
      body: "When a guest places a food order or makes a booking, the flag agent retrieves their known dietary restrictions and cross-checks against the order payload. No hardcoded allergen lists — the LLM decides conflicts by reasoning over memory.",
    },
    {
      title: "Role Memory",
      icon: "👥",
      body: "Ops artifacts (briefings, digests, group briefs) are written into role-specific memory namespaces (role_gm, role_front_desk, role_events). Role memory persists across staff turnover — the role retains institutional knowledge even as individuals change.",
    },
    {
      title: "Monthly Ops Digest",
      icon: "📊",
      body: "The digest agent aggregates memory across all guests for a given period and synthesises a property-wide summary for the General Manager: top themes, service recovery patterns, VIP preferences, and group event highlights.",
    },
    {
      title: "Memory Retention Policies",
      icon: "🔐",
      body: "Guests choose their retention preference at sign-in: Persistent (memories never expire), Stay-only (expires after 1–7 days), or Anonymous (GDPR — no memory written at all). The TTL is applied at the session level.",
    },
  ];

  return (
    <OpsViewWrapper>
      <div style={{ borderBottom: "1px solid rgba(230,32,32,0.1)", paddingBottom: "1rem" }}>
        <h2 style={{ margin: "0 0 0.4rem", fontSize: "1.5rem", fontWeight: 700, color: "#1A1A1A" }}>How It Works</h2>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
          Architecture overview for the Couchbase Agent Memory Hotel demo.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: "1rem" }}>
        {sections.map((s) => (
          <div key={s.title} style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)", borderRadius: 12, padding: "1.2rem 1.4rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.5rem" }}>
              <span style={{ fontSize: "1.3rem" }}>{s.icon}</span>
              <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{s.title}</div>
            </div>
            <div style={{ fontSize: "0.84rem", color: "var(--text-muted)", lineHeight: 1.65 }}>{s.body}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: "1.5rem", padding: "1rem 1.2rem", background: "rgba(230,32,32,0.04)", border: "1px solid rgba(230,32,32,0.12)", borderRadius: 10, fontSize: "0.8rem", color: "var(--text-muted)" }}>
        <strong style={{ color: "var(--brand-red)" }}>Powered by Couchbase Agent Memory</strong> — a purpose-built memory layer for AI agents, backed by Couchbase&apos;s vector search and full-text capabilities.
      </div>
    </OpsViewWrapper>
  );
}
