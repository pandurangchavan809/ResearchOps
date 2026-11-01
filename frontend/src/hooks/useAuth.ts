import { create } from "zustand";

import { api, refreshSession, setSessionLostHandler } from "@/api";
import type { Credits, User } from "@/types";

interface AuthState {
  status: "loading" | "anonymous" | "authenticated";
  user: User | null;
  /** Restores the session from the refresh cookie when the app opens. */
  restore: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, newPassword: string, confirmPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  setCredits: (credits: Credits) => void;
}

export const useAuth = create<AuthState>((set) => {
  setSessionLostHandler(() => set({ status: "anonymous", user: null }));
  return {
    status: "loading",
    user: null,
    restore: async () => {
      try {
        const session = await refreshSession();
        set({ status: "authenticated", user: session.user });
      } catch {
        set({ status: "anonymous", user: null });
      }
    },
    login: async (email, password) => {
      const session = await api.login(email, password);
      set({ status: "authenticated", user: session.user });
    },
    register: async (email, newPassword, confirmPassword) => {
      const session = await api.register(email, newPassword, confirmPassword);
      set({ status: "authenticated", user: session.user });
    },
    logout: async () => {
      await api.logout();
      set({ status: "anonymous", user: null });
    },
    setCredits: (credits) => set((state) => (state.user ? { user: { ...state.user, credits } } : state)),
  };
});
