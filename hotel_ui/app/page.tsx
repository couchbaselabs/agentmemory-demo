"use client";
import { useRouter } from "next/navigation";
import HotelHeader from "@/components/shared/HotelHeader";

export default function LandingPage() {
  const router = useRouter();

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <HotelHeader />

      <div style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-start",
        padding: "2.5rem 2rem 3rem",
      }}>
        {/* Hero text */}
        <div style={{ textAlign: "center", marginBottom: "2.5rem" }}>
          <div style={{ fontSize: "2.4rem", fontWeight: 800, color: "#1A1A1A", fontFamily: "Inter, sans-serif", letterSpacing: "-0.02em", marginBottom: "0.6rem" }}>
            Welcome to the Hotel
          </div>
          <div style={{ fontSize: "1rem", color: "rgba(26,26,26,0.45)", letterSpacing: "0.02em", fontFamily: "Inter, sans-serif" }}>
            Powered by Couchbase Agent Memory. Choose your portal to continue.
          </div>
        </div>

        {/* Mode cards */}
        <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", justifyContent: "center" }}>
          <ModeCard
            emoji="🛎️"
            title="Guest Concierge"
            description="Chat with a personalised AI concierge that remembers your preferences, dietary needs, and past stays."
            cta="Sign in as guest"
            onClick={() => router.push("/guest")}
          />
          <ModeCard
            emoji="🏨"
            title="Hotel Operations"
            description="Staff portal for pre-arrival briefings, allergy scans, guest management, and role-based memory tools."
            cta="Sign in as staff"
            onClick={() => router.push("/ops")}
          />
        </div>

        {/* Dev links */}
        <div style={{ marginTop: "auto", paddingTop: "3rem", display: "flex", gap: "0.75rem" }}>
          <a
            href={`${process.env.NEXT_PUBLIC_AGENTMEM_URL || "http://localhost:8080"}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: "0.78rem",
              fontWeight: 500,
              color: "rgba(26,26,26,0.4)",
              padding: "0.35rem 0.9rem",
              border: "1px solid rgba(26,26,26,0.1)",
              borderRadius: 6,
              textDecoration: "none",
              background: "rgba(255,255,255,0.5)",
              transition: "color 0.15s, border-color 0.15s",
            }}
            onMouseEnter={(e) => { const el = e.currentTarget; el.style.color = "#1A1A1A"; el.style.borderColor = "rgba(26,26,26,0.25)"; }}
            onMouseLeave={(e) => { const el = e.currentTarget; el.style.color = "rgba(26,26,26,0.4)"; el.style.borderColor = "rgba(26,26,26,0.1)"; }}
          >
            AgentMemory Server ↗
          </a>
        </div>
      </div>
    </div>
  );
}

function ModeCard({ emoji, title, description, cta, onClick }: {
  emoji: string;
  title: string;
  description: string;
  cta: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 360,
        padding: "3rem 2.5rem",
        background: "rgba(255,255,255,0.72)",
        border: "1px solid rgba(230,32,32,0.14)",
        borderRadius: 16,
        cursor: "pointer",
        textAlign: "center",
        transition: "box-shadow 0.18s, border-color 0.18s, transform 0.18s",
        fontFamily: "Inter, sans-serif",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "0.85rem",
        backdropFilter: "blur(6px)",
        boxShadow: "0 2px 12px rgba(0,0,0,0.05)",
      }}
      onMouseEnter={(e) => {
        const el = e.currentTarget;
        el.style.boxShadow = "0 10px 36px rgba(230,32,32,0.13)";
        el.style.borderColor = "rgba(230,32,32,0.32)";
        el.style.transform = "translateY(-4px)";
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget;
        el.style.boxShadow = "0 2px 12px rgba(0,0,0,0.05)";
        el.style.borderColor = "rgba(230,32,32,0.14)";
        el.style.transform = "none";
      }}
    >
      {/* Emoji in a pill */}
      <div style={{
        width: 80,
        height: 80,
        borderRadius: "50%",
        background: "rgba(230,32,32,0.06)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "2.4rem",
        flexShrink: 0,
      }}>
        {emoji}
      </div>

      <div style={{ fontWeight: 700, fontSize: "1.25rem", color: "#1A1A1A" }}>{title}</div>

      <div style={{ fontSize: "0.88rem", color: "rgba(26,26,26,0.52)", lineHeight: 1.7, maxWidth: 260 }}>
        {description}
      </div>

      <div style={{
        marginTop: "0.5rem",
        fontSize: "0.82rem",
        fontWeight: 600,
        color: "rgba(230,32,32,0.75)",
        display: "flex",
        alignItems: "center",
        gap: "0.3rem",
      }}>
        {cta} <span style={{ fontSize: "0.9rem" }}>→</span>
      </div>
    </button>
  );
}
