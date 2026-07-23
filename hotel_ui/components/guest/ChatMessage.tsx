"use client";
import { useState } from "react";
import type { ChatMsg, MemoryRecord } from "@/lib/types";
import StatusPipeline from "@/components/shared/StatusPipeline";

function MemoryRecordItem({ rec }: { rec: MemoryRecord }) {
  const [open, setOpen] = useState(false);
  const preview = rec.kind === "chat"
    ? (rec.user_content || rec.assistant_content || "")
    : (rec.text || "");
  const snippet = preview.length > 90 ? preview.slice(0, 90) + "…" : preview;

  return (
    <div className="expander" style={{ marginTop: "0.3rem" }}>
      <div className="expander-header" onClick={() => setOpen(!open)}>
        <span>
          <span className="memory-pill">{rec.kind}</span>
          {" "}
          <span style={{ color: "rgba(26,26,26,0.75)", fontSize: "0.78rem" }}>{snippet}</span>
        </span>
        <span style={{ fontSize: "0.7rem", opacity: 0.5 }}>{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div className="expander-body" style={{ fontSize: "0.82rem", lineHeight: 1.6 }}>
          {rec.kind === "chat" ? (
            <>
              {rec.user_content && (
                <div style={{ marginBottom: "0.3rem" }}>
                  <span style={{ color: "rgba(230,32,32,0.7)", fontWeight: 600, fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>Guest</span>
                  <div style={{ color: "rgba(26,26,26,0.85)", marginTop: "0.15rem" }}>{rec.user_content}</div>
                </div>
              )}
              {rec.assistant_content && (
                <div>
                  <span style={{ color: "rgba(230,32,32,0.7)", fontWeight: 600, fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>Concierge</span>
                  <div style={{ color: "rgba(26,26,26,0.85)", marginTop: "0.15rem" }}>{rec.assistant_content}</div>
                </div>
              )}
            </>
          ) : (
            <div style={{ color: "rgba(26,26,26,0.85)" }}>{rec.text}</div>
          )}
          {rec.ingested_at && (
            <div style={{ marginTop: "0.4rem", fontSize: "0.7rem", color: "rgba(26,26,26,0.4)" }}>
              ingested: {rec.ingested_at}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  msg: ChatMsg;
}

export default function ChatMessage({ msg }: Props) {
  // Pipeline starts open while streaming (no content yet), then stays at user's last toggle
  const isStreaming = !msg.content && msg.role === "assistant";
  const [pipelineOpen, setPipelineOpen] = useState(true); // default open
  const [memoriesOpen, setMemoriesOpen] = useState(false);

  const _tsDate = msg.timestamp ? new Date(msg.timestamp) : null
  const ts = _tsDate && !isNaN(_tsDate.getTime())
    ? _tsDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";

  if (msg.role === "user") {
    return (
      <div className="msg-guest">
        <div style={{ maxWidth: "86%", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.2rem" }}>
          <div className="bubble-guest">{msg.content}</div>
          {ts && <span className="bubble-timestamp">{ts}</span>}
        </div>
      </div>
    );
  }

  return (
    <div className="msg-concierge">
      <div className="concierge-avatar">C</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="concierge-label">Concierge</div>

        {isStreaming ? (
          /* While waiting for response — friendly status, no confusing pending steps */
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.6rem 0", color: "rgba(26,26,26,0.5)", fontSize: "0.82rem", fontStyle: "italic" }}>
            <span style={{ display: "inline-flex", gap: "0.18rem" }}>
              {[0, 1, 2].map(i => (
                <span key={i} style={{ width: 5, height: 5, borderRadius: "50%", background: "rgba(230,32,32,0.4)", display: "inline-block", animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }} />
              ))}
            </span>
            Concierge is preparing your response…
          </div>
        ) : (
          <div className="bubble-concierge">{msg.content}</div>
        )}

        {ts && !isStreaming && <span className="bubble-timestamp">{ts}</span>}

        {/* Pipeline — only shown after response arrives, hidden for historical messages */}
        {!msg.historical && !isStreaming && msg.statusSteps && msg.statusSteps.length > 0 && (
          <div className="expander" style={{ marginTop: "0.5rem" }}>
            <div className="expander-header" onClick={() => setPipelineOpen(!pipelineOpen)}>
              <span style={{ fontSize: "0.78rem", fontWeight: 500, color: "rgba(26,26,26,0.7)" }}>View pipeline</span>
              <span style={{ fontSize: "0.7rem", opacity: 0.5 }}>{pipelineOpen ? "▲" : "▼"}</span>
            </div>
            {pipelineOpen && (
              <div style={{ padding: "0.5rem 0.75rem 0.65rem" }}>
                <StatusPipeline steps={msg.statusSteps} totalMs={msg.totalMs} />
              </div>
            )}
          </div>
        )}

        {/* Memory update ms is now shown inside the pipeline step — no separate card */}

        {/* Retrieved memories — hidden for historical session messages */}
        {!msg.historical && msg.memoryRecords && msg.memoryRecords.length > 0 && (
          <div className="expander" style={{ marginTop: "0.4rem" }}>
            <div className="expander-header" onClick={() => setMemoriesOpen(!memoriesOpen)}>
              <span style={{ fontSize: "0.78rem" }}>Retrieved memories ({msg.memoryRecords.length})</span>
              <span style={{ fontSize: "0.7rem", opacity: 0.5 }}>{memoriesOpen ? "▲" : "▼"}</span>
            </div>
            {memoriesOpen && (
              <div className="expander-body" style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                {msg.memoryRecords.map((r) => (
                  <MemoryRecordItem key={r.block_id} rec={r} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
