"use client";
import { useState } from "react";

interface Props {
  title: string;
  description: string;
  passwordLabel?: string;
  expectedPassword: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
}

export default function DeleteDialog({
  title,
  description,
  passwordLabel = "Enter password to confirm deletion:",
  expectedPassword,
  onConfirm,
  onCancel,
  confirmLabel = "Confirm Delete",
}: Props) {
  const [pwd, setPwd] = useState("");
  const [error, setError] = useState("");

  function handleConfirm() {
    if (pwd !== expectedPassword) {
      setError("Incorrect password.");
      return;
    }
    onConfirm();
  }

  return (
    <div className="dialog-overlay">
      <div className="dialog-card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1rem" }}>
          <span style={{ fontSize: "1.3rem" }}>⚠️</span>
          <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700 }}>{title}</h3>
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: "0 0 1.2rem" }}>
          {description}
        </p>
        <div style={{ marginBottom: "1rem" }}>
          <label className="form-label">{passwordLabel}</label>
          <input
            type="password"
            className="form-input"
            value={pwd}
            onChange={(e) => { setPwd(e.target.value); setError(""); }}
            onKeyDown={(e) => e.key === "Enter" && handleConfirm()}
            autoFocus
          />
          {error && <div style={{ color: "#dc2626", fontSize: "0.78rem", marginTop: "0.3rem" }}>{error}</div>}
        </div>
        <div style={{ display: "flex", gap: "0.6rem", justifyContent: "flex-end" }}>
          <button className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="btn-danger" onClick={handleConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
