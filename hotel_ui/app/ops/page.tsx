"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useOpsStore } from "@/store/opsStore";
import { opsLogin, getRoles } from "@/lib/api";
import HotelHeader from "@/components/shared/HotelHeader";
import type { OpsRole } from "@/lib/types";

const ROLE_ORDER = ["role_gm", "role_front_desk", "role_events", "role_facilities"];

export default function OpsLoginPage() {
  const store = useOpsStore();
  const router = useRouter();
  const { authenticated } = store;

  const [roles, setRoles] = useState<Record<string, OpsRole>>({});
  const [selectedRole, setSelectedRole] = useState("role_gm");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (authenticated) router.push(`/ops/${store.activeView}`);
  }, [authenticated]);

  useEffect(() => {
    getRoles().then((r) => setRoles(r.roles)).catch(() => {});
  }, []);

  async function handleLogin() {
    setError(""); setLoading(true);
    try {
      const result = await opsLogin(selectedRole, password);
      store.setRole(result.role_id, result.role);
      router.push(`/ops/${result.role.default_view}`);
    } catch (e: unknown) {
      setError((e as Error).message || "Invalid password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh" }}>
      <HotelHeader portalLabel="Operations Portal" />
      <div className="login-container">
        <div style={{
          maxWidth: 420,
          margin: "0 auto",
          padding: "2.5em",
          background: "rgba(255,255,255,0.7)",
          border: "1px solid rgba(230,32,32,0.15)",
          borderRadius: 12,
          width: "100%",
        }}>
          {/* Card title — matches guest login exactly */}
          <div style={{ textAlign: "center", fontSize: "2em", fontWeight: 700, color: "#1A1A1A", marginBottom: "0.5em", fontFamily: "Inter, sans-serif" }}>
            Couchbase Agent Memory Hotel
          </div>
          <div style={{ textAlign: "center", color: "rgba(230,32,32,0.5)", marginBottom: "1.5em", fontSize: "0.9em", letterSpacing: "0.1em" }}>
            Staff Portal
          </div>

          {/* Role selector */}
          <div style={{ marginBottom: "0.8rem" }}>
            <label className="form-label">Role:</label>
            <select
              className="form-select"
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value)}
            >
              {ROLE_ORDER.filter((r) => roles[r]).map((rid) => (
                <option key={rid} value={rid}>
                  {roles[rid].name} — {roles[rid].tagline}
                </option>
              ))}
            </select>
          </div>

          {/* Password */}
          <div style={{ marginBottom: "1.2rem" }}>
            <label className="form-label">Password:</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              placeholder="Enter password"
            />
          </div>

          {error && (
            <div style={{ background: "rgba(198,32,32,0.06)", border: "1px solid rgba(198,32,32,0.25)", borderRadius: 6, padding: "0.6rem 0.85rem", fontSize: "0.83rem", color: "#C62020", marginBottom: "0.8rem" }}>
              {error}
            </div>
          )}

          <button className="btn-primary" style={{ width: "100%" }} onClick={handleLogin} disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </div>
      </div>
    </div>
  );
}
