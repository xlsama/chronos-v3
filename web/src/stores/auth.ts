import { create } from "zustand";
import type { UserInfo } from "@/api/auth";

const TOKEN_KEY = "chronos_token";

interface AuthState {
  user: UserInfo | null;
  token: string | null;
  setAuth: (user: UserInfo, token: string) => void;
  setUser: (user: UserInfo) => void;
  clearAuth: () => void;
  hydrate: () => string | null;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  setAuth: (user, token) => {
    localStorage.setItem(TOKEN_KEY, token);
    set({ user, token });
  },
  setUser: (user) => {
    set({ user });
  },
  clearAuth: () => {
    localStorage.removeItem(TOKEN_KEY);
    set({ user: null, token: null });
  },
  hydrate: () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && !get().token) {
      set({ token });
    }
    return token;
  },
}));
