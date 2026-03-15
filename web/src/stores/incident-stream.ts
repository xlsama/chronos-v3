import { create } from "zustand";
import type { SSEEvent } from "@/lib/types";

interface IncidentStreamState {
  events: SSEEvent[];
  isConnected: boolean;
  thinkingContent: string;
  addEvent: (event: SSEEvent) => void;
  appendThinking: (content: string) => void;
  clearThinking: () => void;
  setConnected: (connected: boolean) => void;
  reset: () => void;
}

export const useIncidentStreamStore = create<IncidentStreamState>((set) => ({
  events: [],
  isConnected: false,
  thinkingContent: "",

  addEvent: (event) =>
    set((state) => ({ events: [...state.events, event] })),

  appendThinking: (content) =>
    set((state) => ({ thinkingContent: state.thinkingContent + content })),

  clearThinking: () => set({ thinkingContent: "" }),

  setConnected: (connected) => set({ isConnected: connected }),

  reset: () =>
    set({ events: [], isConnected: false, thinkingContent: "" }),
}));
