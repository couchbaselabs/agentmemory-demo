"use client";
import { useState, useRef } from "react";
import { useGuestStore } from "@/store/guestStore";
import { streamSSE } from "@/lib/api";
import type { ChatMsg, StatusStep } from "@/lib/types";

export default function ChatInput() {
  const store = useGuestStore();
  const { activeUser, currentSessionId, isSessionReadonly, isStreaming, memoryPolicy } = store;

  const [text, setText] = useState("");
  const abortRef = useRef<(() => void) | null>(null);

  const disabled = !currentSessionId || isSessionReadonly || isStreaming;
  const placeholder = !currentSessionId
    ? "Click New Chat to start a conversation…"
    : isSessionReadonly
    ? "Viewing a previous session (read-only)…"
    : `Message your concierge, ${activeUser?.name ?? "Guest"}…`;

  function handleSend() {
    const msg = text.trim();
    if (!msg || disabled || !activeUser || !currentSessionId) return;
    setText("");

    const userMsg: ChatMsg = {
      id: typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2),
      role: "user",
      content: msg,
      timestamp: new Date().toISOString(),
    };
    store.addMessage(userMsg);

    const assistantMsg: ChatMsg = {
      id: typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2),
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      statusSteps: [{ step: "Query rewriter", state: "running" }],
    };
    store.addMessage(assistantMsg);
    store.setIsStreaming(true);

    const stepMap: StatusStep[] = [];

    abortRef.current = streamSSE(
      "/chat/stream",
      {
        user_id: activeUser.user_id,
        session_id: currentSessionId,
        message: msg,
        memory_mode: memoryPolicy.mode,
        memory_ttl_seconds: memoryPolicy.ttlSeconds,
        speaker_name: activeUser.name,
      },
      (type, data) => {
        if (type === "status") {
          const step = data as unknown as StatusStep;
          stepMap.push(step);
          store.updateLastAssistantMessage({ statusSteps: [...stepMap] });
        } else if (type === "status_complete") {
          const d = data as { steps: StatusStep[]; total_ms: number };
          store.updateLastAssistantMessage({ statusSteps: d.steps, totalMs: d.total_ms });
        } else if (type === "response") {
          const d = data as { content: string; timestamp: string };
          store.updateLastAssistantMessage({
            content: d.content,
            timestamp: d.timestamp,
          });
        } else if (type === "memory_update") {
          const d = data as { save_ms: number };
          store.updateLastAssistantMessage({ memoryUpdateMs: d.save_ms });
        } else if (type === "memory_records") {
          const d = data as { records: unknown[] };
          store.updateLastAssistantMessage({
            memoryRecords: d.records as ChatMsg["memoryRecords"],
          });
        } else if (type === "error") {
          const d = data as { message: string };
          store.updateLastAssistantMessage({ content: `Error: ${d.message}` });
          store.setIsStreaming(false);
        }
      },
      () => store.setIsStreaming(false),
      (err) => {
        store.updateLastAssistantMessage({ content: `Error: ${err}` });
        store.setIsStreaming(false);
      },
    );
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="chat-input-bar">
      <textarea
        className="chat-input-field"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
      />
      <button className="chat-send-btn" onClick={handleSend} disabled={disabled || !text.trim()}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 2L11 13" /><path d="M22 2L15 22 11 13 2 9l20-7z" />
        </svg>
      </button>
    </div>
  );
}
