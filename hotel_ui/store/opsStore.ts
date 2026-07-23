"use client";
import { create } from "zustand";
import type { GuestUser, OpsRole, SafetyItem, CallLog, BriefingResult } from "@/lib/types";

interface OpsState {
  authenticated: boolean;
  activeRoleId: string | null;
  activeRole: OpsRole | null;
  activeView: string;

  guestUsers: GuestUser[];
  guestsLoaded: boolean;

  briefings: Record<string, BriefingResult>;
  safetyItems: SafetyItem[];
  safetyScannedAt: string | null;
  callLogs: CallLog[];
  digest: Record<string, unknown> | null;
  digestGeneratedAt: string | null;
  groupBriefs: unknown[];
  flags: unknown[];

  showDeleteConfirmation: boolean;
  deletionUserId: string | null;
  deletionComplete: boolean;

  roles: Record<string, OpsRole>;

  // actions
  setAuthenticated: (v: boolean) => void;
  setRole: (id: string, role: OpsRole) => void;
  setActiveView: (v: string) => void;
  setGuests: (g: GuestUser[]) => void;
  setBriefing: (guestId: string, r: BriefingResult) => void;
  setSafetyItems: (items: SafetyItem[], ts: string) => void;
  addCallLog: (log: CallLog) => void;
  setDigest: (d: Record<string, unknown>, ts: string) => void;
  addGroupBrief: (b: unknown) => void;
  addFlag: (f: unknown) => void;
  setShowDeleteConfirmation: (v: boolean, userId?: string) => void;
  setDeletionComplete: (v: boolean) => void;
  setRoles: (r: Record<string, OpsRole>) => void;
  logout: () => void;
}

export const useOpsStore = create<OpsState>((set) => ({
  authenticated: false,
  activeRoleId: null,
  activeRole: null,
  activeView: "dashboard",

  guestUsers: [],
  guestsLoaded: false,

  briefings: {},
  safetyItems: [],
  safetyScannedAt: null,
  callLogs: [],
  digest: null,
  digestGeneratedAt: null,
  groupBriefs: [],
  flags: [],

  showDeleteConfirmation: false,
  deletionUserId: null,
  deletionComplete: false,

  roles: {},

  setAuthenticated: (v) => set({ authenticated: v }),
  setRole: (id, role) => set({ activeRoleId: id, activeRole: role, activeView: role.default_view, authenticated: true }),
  setActiveView: (v) => set({ activeView: v }),
  setGuests: (g) => set({ guestUsers: g, guestsLoaded: true }),
  setBriefing: (guestId, r) =>
    set((s) => ({ briefings: { ...s.briefings, [guestId]: r } })),
  setSafetyItems: (items, ts) => set({ safetyItems: items, safetyScannedAt: ts }),
  addCallLog: (log) => set((s) => ({ callLogs: [log, ...s.callLogs].slice(0, 50) })),
  setDigest: (d, ts) => set({ digest: d, digestGeneratedAt: ts }),
  addGroupBrief: (b) => set((s) => ({ groupBriefs: [b, ...s.groupBriefs] })),
  addFlag: (f) => set((s) => ({ flags: [f, ...s.flags].slice(0, 20) })),
  setShowDeleteConfirmation: (v, userId) =>
    set({ showDeleteConfirmation: v, deletionUserId: userId ?? null }),
  setDeletionComplete: (v) => set({ deletionComplete: v }),
  setRoles: (r) => set({ roles: r }),
  logout: () =>
    set({
      authenticated: false,
      activeRoleId: null,
      activeRole: null,
      activeView: "dashboard",
    }),
}));
