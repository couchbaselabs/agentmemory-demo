"use client";
import { useEffect } from "react";
import { useGuestStore } from "@/store/guestStore";
import { getProfile } from "@/lib/api";

export default function ProfileOverview() {
  const { profileOverview, profileLoading, activeUser, profileUserId,
          setProfileOverview, setProfileLoading, setProfileUserId } = useGuestStore();

  async function loadProfile() {
    if (!activeUser || profileLoading) return;
    setProfileLoading(true);
    try {
      const r = await getProfile(activeUser.user_id);
      setProfileOverview(r.profile);
      setProfileUserId(activeUser.user_id);
    } catch { /* ignore */ }
    setProfileLoading(false);
  }

  // Auto-load when user logs in or changes
  useEffect(() => {
    if (activeUser && activeUser.user_id !== profileUserId && !profileLoading) {
      loadProfile();
    }
  }, [activeUser?.user_id]);

  const cardStyle: React.CSSProperties = {
    background: "rgba(255,255,255,0.6)",
    border: "1px solid rgba(230,32,32,0.12)",
    borderRadius: 8,
    padding: "1rem",
    margin: "0.5rem 0",
    fontSize: "0.85rem",
    lineHeight: 1.6,
  };

  return (
    <div style={cardStyle}>
      <div style={{ color: "rgba(230,32,32,0.8)", fontWeight: 600, marginBottom: "0.5rem" }}>
        Profile Overview
      </div>
      {profileLoading ? (
        <div style={{ color: "rgba(26,26,26,0.45)", fontStyle: "italic" }}>Loading profile…</div>
      ) : profileOverview && !profileOverview.empty ? (
        <>
          {profileOverview.preferences && (
            <div style={{ color: "rgba(26,26,26,0.85)", marginBottom: "0.3rem" }}>
              <strong>Likes:</strong> {profileOverview.preferences}
            </div>
          )}
          {profileOverview.dislikes && (
            <div style={{ color: "rgba(26,26,26,0.85)", marginBottom: "0.3rem" }}>
              <strong>Dislikes:</strong> {profileOverview.dislikes}
            </div>
          )}
          {profileOverview.complaints && (
            <div style={{ color: "rgba(26,26,26,0.85)" }}>
              <strong>Previous Complaints:</strong> {profileOverview.complaints}
            </div>
          )}
        </>
      ) : (
        <div style={{ color: "rgba(26,26,26,0.55)", fontStyle: "italic" }}>
          {profileOverview === null
            ? "No memories yet — start a chat to build your profile."
            : "Profile unavailable."}
        </div>
      )}
      <button
        className="btn-secondary"
        style={{ marginTop: "0.6rem", width: "100%", fontSize: "0.78rem" }}
        onClick={loadProfile}
        disabled={profileLoading}
      >
        {profileLoading ? "Updating…" : "Update Profile"}
      </button>
    </div>
  );
}
