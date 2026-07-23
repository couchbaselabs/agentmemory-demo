"use client";
import { useEffect, useState } from "react";

interface Props {
  message: string;
  onDone: () => void;
  durationMs?: number;
}

export default function Toast({ message, onDone, durationMs = 3500 }: Props) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const hide = setTimeout(() => setVisible(false), durationMs - 400);
    const done = setTimeout(onDone, durationMs);
    return () => { clearTimeout(hide); clearTimeout(done); };
  }, []);

  return (
    <div style={{
      position: "fixed",
      bottom: "2rem",
      left: "50%",
      transform: "translateX(-50%)",
      background: "rgba(76,175,130,0.95)",
      color: "#fff",
      padding: "0.75rem 1.5rem",
      borderRadius: 10,
      fontSize: "0.88rem",
      fontWeight: 500,
      boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
      zIndex: 999,
      transition: "opacity 0.4s ease",
      opacity: visible ? 1 : 0,
      whiteSpace: "nowrap",
      fontFamily: "Inter, sans-serif",
    }}>
      ✓ {message}
    </div>
  );
}
