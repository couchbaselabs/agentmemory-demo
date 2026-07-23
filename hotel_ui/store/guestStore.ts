"use client";
import { create } from "zustand";
import type { GuestUser, SessionInfo, ChatMsg, ProfileOverview, MemoryMode, MemoryPolicy } from "@/lib/types";

interface GuestState {
  // auth
  authenticated: boolean;
  loginMode: "signin" | "newuser" | "user_created";
  loginAttempts: number;
  createdUserName: string | null;
  createdUserMs: number;

  // active user & session
  activeUser: GuestUser | null;
  currentSessionId: string | null;
  allSessions: SessionInfo[];
  isSessionReadonly: boolean;
  endedSessionIds: Set<string>;

  // chat
  chatMessages: ChatMsg[];
  isStreaming: boolean;

  // profile
  profileOverview: ProfileOverview | null;
  profileLoading: boolean;
  profileUserId: string | null;

  // memory policy
  memoryPolicy: MemoryPolicy;

  // delete
  showDeleteConfirmation: boolean;
  deletionComplete: boolean;

  // all loaded users (for login dropdown)
  allUsers: GuestUser[];
  usersLoaded: boolean;

  // actions
  setAuthenticated: (v: boolean) => void;
  setLoginMode: (m: "signin" | "newuser" | "user_created") => void;
  setActiveUser: (u: GuestUser | null) => void;
  setSessions: (s: SessionInfo[]) => void;
  setCurrentSession: (id: string | null, readonly?: boolean) => void;
  addEndedSession: (id: string) => void;
  addMessage: (m: ChatMsg) => void;
  setMessages: (msgs: ChatMsg[]) => void;
  updateLastAssistantMessage: (patch: Partial<ChatMsg>) => void;
  clearMessages: () => void;
  setIsStreaming: (v: boolean) => void;
  setProfileOverview: (p: ProfileOverview | null) => void;
  setProfileLoading: (v: boolean) => void;
  setProfileUserId: (id: string | null) => void;
  setMemoryPolicy: (p: MemoryPolicy) => void;
  setShowDeleteConfirmation: (v: boolean) => void;
  setDeletionComplete: (v: boolean) => void;
  setAllUsers: (u: GuestUser[]) => void;
  setCreatedUser: (name: string, ms: number) => void;
  logout: () => void;
}

export const useGuestStore = create<GuestState>((set, get) => ({
  authenticated: false,
  loginMode: "signin",
  loginAttempts: 0,
  createdUserName: null,
  createdUserMs: 0,
  activeUser: null,
  currentSessionId: null,
  allSessions: [],
  isSessionReadonly: false,
  endedSessionIds: new Set(),
  chatMessages: [],
  isStreaming: false,
  profileOverview: null,
  profileLoading: false,
  profileUserId: null,
  memoryPolicy: { mode: "persistent", ttlSeconds: 0, ttlLabel: "Forever" },
  showDeleteConfirmation: false,
  deletionComplete: false,
  allUsers: [],
  usersLoaded: false,

  setAuthenticated: (v) => set({ authenticated: v }),
  setLoginMode: (m) => set({ loginMode: m }),
  setActiveUser: (u) => set({ activeUser: u }),
  setSessions: (s) => set({ allSessions: s }),
  setCurrentSession: (id, readonly = false) =>
    set({ currentSessionId: id, isSessionReadonly: readonly, chatMessages: [] }),
  addEndedSession: (id) =>
    set((s) => ({ endedSessionIds: new Set(Array.from(s.endedSessionIds).concat(id)) })),
  addMessage: (m) => set((s) => ({ chatMessages: [...s.chatMessages, m] })),
  setMessages: (msgs) => set({ chatMessages: msgs }),
  updateLastAssistantMessage: (patch) =>
    set((s) => {
      const msgs = [...s.chatMessages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], ...patch };
          break;
        }
      }
      return { chatMessages: msgs };
    }),
  clearMessages: () => set({ chatMessages: [] }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  setProfileOverview: (p) => set({ profileOverview: p }),
  setProfileLoading: (v) => set({ profileLoading: v }),
  setProfileUserId: (id) => set({ profileUserId: id }),
  setMemoryPolicy: (p) => set({ memoryPolicy: p }),
  setShowDeleteConfirmation: (v) => set({ showDeleteConfirmation: v }),
  setDeletionComplete: (v) => set({ deletionComplete: v }),
  setAllUsers: (u) => set({ allUsers: u, usersLoaded: true }),
  setCreatedUser: (name, ms) =>
    set({ createdUserName: name, createdUserMs: ms, loginMode: "user_created" }),
  logout: () =>
    set({
      authenticated: false,
      loginMode: "signin",
      activeUser: null,
      currentSessionId: null,
      allSessions: [],
      chatMessages: [],
      profileOverview: null,
      profileUserId: null,
      isSessionReadonly: false,
      endedSessionIds: new Set(),
      showDeleteConfirmation: false,
      deletionComplete: false,
      // Clear cached user list so the login dropdown re-fetches from the backend
      allUsers: [],
      usersLoaded: false,
    }),
}));
