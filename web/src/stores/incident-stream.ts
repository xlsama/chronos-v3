import { create } from "zustand";
import type { SSEEvent } from "@/lib/types";

interface IncidentStreamState {
  events: SSEEvent[];
  gatherContextEvents: SSEEvent[];
  isConnected: boolean;
  thinkingContent: string;
  subAgentThinkingContent: string;
  addEvent: (event: SSEEvent) => void;
  appendThinking: (content: string) => void;
  clearThinking: () => void;
  appendSubAgentThinking: (content: string) => void;
  clearSubAgentThinking: () => void;
  setConnected: (connected: boolean) => void;
  reset: () => void;
}

export const useIncidentStreamStore = create<IncidentStreamState>((set) => ({
  events: [],
  gatherContextEvents: [],
  isConnected: false,
  thinkingContent: "",
  subAgentThinkingContent: "",

  addEvent: (event) => {
    const phase = (event.data.phase as string) || "";
    if (phase === "gather_context") {
      set((state) => ({
        gatherContextEvents: [...state.gatherContextEvents, event],
      }));
    } else {
      set((state) => ({ events: [...state.events, event] }));
    }
  },

  appendThinking: (content) =>
    set((state) => ({ thinkingContent: state.thinkingContent + content })),

  clearThinking: () => set({ thinkingContent: "" }),

  appendSubAgentThinking: (content) =>
    set((state) => ({
      subAgentThinkingContent: state.subAgentThinkingContent + content,
    })),

  clearSubAgentThinking: () => set({ subAgentThinkingContent: "" }),

  setConnected: (connected) => set({ isConnected: connected }),

  reset: () =>
    set({
      events: [],
      gatherContextEvents: [],
      isConnected: false,
      thinkingContent: "",
      subAgentThinkingContent: "",
    }),
}));
