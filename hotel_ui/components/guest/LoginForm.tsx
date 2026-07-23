"use client";
import { useState, useEffect } from "react";
import { useGuestStore } from "@/store/guestStore";
import { login, listUsers, createUser } from "@/lib/api";
import type { MemoryMode } from "@/lib/types";

const SECONDS_PER_DAY = 86400;

export default function LoginForm() {
  const store = useGuestStore();
  const { loginMode, allUsers, usersLoaded, createdUserName, createdUserMs } = store;

  const [selectedUserId, setSelectedUserId] = useState("");
  const [password, setPassword] = useState("");
  const [memoryMode, setMemoryMode] = useState<MemoryMode>("persistent");
  const [ttlDays, setTtlDays] = useState(3);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  // New user form
  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!usersLoaded) {
      listUsers()
        .then((r) => {
          store.setAllUsers(r.users);
          if (r.users.length > 0) setSelectedUserId(r.users[0].user_id);
        })
        .catch(() => {
          setLoadError(
            "Cannot reach the backend server. Make sure hotel_server.py is running on port 8001."
          );
        });
    }
  }, [usersLoaded]);

  async function handleSignIn() {
    if (!selectedUserId) { setError("Please select a profile."); return; }
    if (!password) { setError("Password required."); return; }
    setError(""); setLoading(true);
    try {
      const days = Math.max(1, Math.round(ttlDays));
      const ttlSeconds = memoryMode === "stay" ? days * SECONDS_PER_DAY : 0;
      const ttlLabel = memoryMode === "stay" ? `${days} day${days !== 1 ? "s" : ""}` : "Forever";
      await login(selectedUserId, password, memoryMode, ttlSeconds, ttlLabel);
      const user = allUsers.find((u) => u.user_id === selectedUserId);
      if (user) store.setActiveUser(user);
      store.setMemoryPolicy({ mode: memoryMode, ttlSeconds, ttlLabel });
      store.setAuthenticated(true);
    } catch (e: unknown) {
      setError((e as Error).message || "Invalid password");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateUser() {
    if (!newName.trim()) { setCreateError("Please enter a name."); return; }
    setCreateError(""); setCreating(true);
    try {
      const result = await createUser(newName.trim());
      store.setCreatedUser(result.name, result.created_ms);
      const r = await listUsers();
      store.setAllUsers(r.users);
    } catch (e: unknown) {
      setCreateError((e as Error).message || "Create failed");
    } finally {
      setCreating(false);
    }
  }

  // ── USER CREATED CONFIRMATION ─────────────────────────────────────────
  if (loginMode === "user_created") {
    return (
      <div className="login-container">
        <div style={{
          maxWidth: 420,
          margin: "0 auto",
          padding: "2.5em",
          background: "rgba(255,255,255,0.7)",
          border: "1px solid rgba(230,32,32,0.15)",
          borderRadius: 12,
        }}>
          <div style={{ textAlign: "center", fontSize: "2em", fontWeight: 700, color: "#1A1A1A", marginBottom: "0.5em", fontFamily: "Inter, sans-serif" }}>
            Couchbase Agent Memory Hotel
          </div>
          <div style={{ textAlign: "center", color: "rgba(230,32,32,0.5)", marginBottom: "1.5em", fontSize: "0.9em", letterSpacing: "0.1em" }}>
            Concierge Portal
          </div>

          {/* st.success equivalent */}
          <div style={{ background: "rgba(76,175,130,0.08)", border: "1px solid rgba(76,175,130,0.3)", borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "0.6rem", color: "rgba(26,26,26,0.85)", fontSize: "0.88rem" }}>
            ✓ Account created for {createdUserName}
          </div>
          {/* st.info equivalent ×2 */}
          <div style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "0.6rem", color: "rgba(26,26,26,0.85)", fontSize: "0.88rem" }}>
            ℹ New user made in {Math.round(createdUserMs)}ms
          </div>
          <div style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", color: "rgba(26,26,26,0.85)", fontSize: "0.88rem" }}>
            ℹ Password: 123 (default)
          </div>

          <button
            className="btn-primary"
            style={{ width: "100%" }}
            onClick={() => store.setLoginMode("signin")}
          >
            Go back to Sign In
          </button>
        </div>
      </div>
    );
  }

  // ── MAIN SIGN-IN / NEW USER CARD ─────────────────────────────────────
  return (
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
        {/* Card title */}
        <div style={{ textAlign: "center", fontSize: "2em", fontWeight: 700, color: "#1A1A1A", marginBottom: "0.5em", fontFamily: "Inter, sans-serif" }}>
          Couchbase Agent Memory Hotel
        </div>
        <div style={{ textAlign: "center", color: "rgba(230,32,32,0.5)", marginBottom: "1.5em", fontSize: "0.9em", letterSpacing: "0.1em" }}>
          Concierge Portal
        </div>

        {/* Mode toggle: two equal buttons side by side */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginBottom: "0.8rem" }}>
          <button
            className="btn-secondary"
            style={{ textAlign: "center", background: loginMode === "signin" ? "rgba(230,32,32,0.09)" : undefined, borderColor: loginMode === "signin" ? "rgba(230,32,32,0.35)" : undefined }}
            onClick={() => { store.setLoginMode("signin"); setError(""); setCreateError(""); }}
          >
            Sign In
          </button>
          <button
            className="btn-secondary"
            style={{ textAlign: "center", background: loginMode === "newuser" ? "rgba(230,32,32,0.09)" : undefined, borderColor: loginMode === "newuser" ? "rgba(230,32,32,0.35)" : undefined }}
            onClick={() => { store.setLoginMode("newuser"); setError(""); setCreateError(""); }}
          >
            New User
          </button>
        </div>

        {/* ── SIGN IN ── */}
        {loginMode === "signin" && (
          <>
            {loadError ? (
              <div style={{ background: "rgba(198,32,32,0.06)", border: "1px solid rgba(198,32,32,0.25)", borderRadius: 6, padding: "0.75rem 1rem", fontSize: "0.83rem", color: "#C62020", lineHeight: 1.5, marginBottom: "0.8rem" }}>
                {loadError}
                <div style={{ marginTop: "0.5rem" }}>
                  <button className="btn-secondary" style={{ fontSize: "0.78rem", width: "auto", minHeight: "auto", padding: "0.3rem 0.7rem" }}
                    onClick={() => { setLoadError(""); store.setAllUsers([]); }}>
                    Retry
                  </button>
                </div>
              </div>
            ) : !usersLoaded ? (
              <div style={{ fontSize: "0.85rem", color: "rgba(26,26,26,0.5)", margin: "0.5rem 0" }}>Loading users…</div>
            ) : allUsers.length === 0 ? (
              <div style={{ background: "rgba(247,148,29,0.08)", border: "1px solid rgba(247,148,29,0.25)", borderRadius: 8, padding: "0.75rem 1rem", fontSize: "0.85rem", color: "#92400e", marginBottom: "0.8rem" }}>
                ⚠ No users available. Please create a new account.
              </div>
            ) : (
              <>
                <div style={{ marginBottom: "0.8rem" }}>
                  <label className="form-label">Select Profile:</label>
                  <select
                    className="form-select"
                    value={selectedUserId}
                    onChange={(e) => setSelectedUserId(e.target.value)}
                  >
                    {allUsers.map((u) => (
                      <option key={u.user_id} value={u.user_id}>{u.name}</option>
                    ))}
                  </select>
                </div>

                <div style={{ marginBottom: "0.8rem" }}>
                  <label className="form-label">Password:</label>
                  <input
                    type="password"
                    className="form-input"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSignIn()}
                    placeholder="Enter password"
                  />
                </div>

                {/* Memory retention section */}
                <div className="panel-section-title" style={{ marginTop: "0.6rem" }}>
                  Memory retention
                </div>
                <div style={{ fontSize: "0.8rem", color: "rgba(26,26,26,0.6)", marginBottom: "0.6rem", lineHeight: 1.5 }}>
                  How should Couchbase Agent Memory treat memories from this stay? You can pick the policy that matches your data preferences.
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", marginBottom: "0.7rem" }}>
                  {([
                    ["persistent", "Persistent — remember me across stays"],
                    ["stay",       "Stay-only — forget after my stay"],
                  ] as [MemoryMode, string][]).map(([val, label]) => (
                    <label key={val} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", cursor: "pointer", color: "#1A1A1A" }}>
                      <input
                        type="radio"
                        name="memory_mode"
                        value={val}
                        checked={memoryMode === val}
                        onChange={() => setMemoryMode(val)}
                        style={{ accentColor: "#E62020" }}
                      />
                      {label}
                    </label>
                  ))}
                </div>

                {memoryMode === "stay" && (
                  <div style={{ marginBottom: "0.8rem" }}>
                    <label className="form-label">Expire memories after how many days?</label>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <input
                        type="number"
                        className="form-input"
                        style={{ width: 90 }}
                        min={1}
                        max={365}
                        value={ttlDays}
                        onChange={(e) => setTtlDays(Math.max(1, parseInt(e.target.value) || 1))}
                      />
                      <span style={{ fontSize: "0.85rem", color: "rgba(26,26,26,0.55)" }}>day{ttlDays !== 1 ? "s" : ""}</span>
                    </div>
                  </div>
                )}

                {error && (
                  <div style={{ background: "rgba(198,32,32,0.06)", border: "1px solid rgba(198,32,32,0.25)", borderRadius: 6, padding: "0.6rem 0.85rem", fontSize: "0.83rem", color: "#C62020", marginBottom: "0.8rem" }}>
                    {error}
                  </div>
                )}

                <button className="btn-primary" style={{ width: "100%" }} onClick={handleSignIn} disabled={loading}>
                  {loading ? "Signing in…" : "Sign In"}
                </button>
              </>
            )}
          </>
        )}

        {/* ── NEW USER ── */}
        {loginMode === "newuser" && (
          <>
            <div style={{ marginBottom: "0.8rem" }}>
              <label className="form-label">Full Name:</label>
              <input
                type="text"
                className="form-input"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateUser()}
                placeholder="e.g., John Doe"
              />
            </div>

            {createError && (
              <div style={{ background: "rgba(198,32,32,0.06)", border: "1px solid rgba(198,32,32,0.25)", borderRadius: 6, padding: "0.6rem 0.85rem", fontSize: "0.83rem", color: "#C62020", marginBottom: "0.8rem" }}>
                {createError}
              </div>
            )}

            <button className="btn-primary" style={{ width: "100%" }} onClick={handleCreateUser} disabled={creating}>
              {creating ? "Creating account…" : "Create Account"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
