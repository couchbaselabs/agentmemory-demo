"use client";
import { useEffect, useRef } from "react";
import { useGuestStore } from "@/store/guestStore";
import ChatMessage from "./ChatMessage";

export default function ChatArea() {
  const { chatMessages } = useGuestStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  if (chatMessages.length === 0) {
    return (
      <div className="chat-area" style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center", opacity: 0.5 }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>💬</div>
          <div style={{ fontSize: "0.88rem", color: "var(--text-muted)" }}>
            Send a message to start your concierge session.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-area">
      {chatMessages.map((m) => (
        <ChatMessage key={m.id} msg={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
