import { create } from "zustand";
import type { SSEEvent } from "@/lib/types";

interface SubAgentState {
  events: SSEEvent[];
  thinkingContent: string;
}

interface IncidentStreamState {
  events: SSEEvent[];
  discoveryAgentState: SubAgentState;
  historyAgentState: SubAgentState;
  kbAgentState: SubAgentState;
  isConnected: boolean;
  thinkingContent: string;
  askHumanQuestion: string | null;
  decidedApprovals: Map<string, string>;
  addEvent: (event: SSEEvent) => void;
  appendThinking: (content: string) => void;
  clearThinking: () => void;
  appendSubAgentThinking: (agent: string, content: string) => void;
  flushSubAgentThinking: (agent: string, timestamp: string) => void;
  addSubAgentEvent: (agent: string, event: SSEEvent) => void;
  setAskHumanQuestion: (question: string | null) => void;
  setApprovalDecided: (approvalId: string, decision: string) => void;
  setConnected: (connected: boolean) => void;
  reset: () => void;
}

const emptySubAgent = (): SubAgentState => ({
  events: [],
  thinkingContent: "",
});

export const useIncidentStreamStore = create<IncidentStreamState>((set) => ({
  events: [],
  discoveryAgentState: emptySubAgent(),
  historyAgentState: emptySubAgent(),
  kbAgentState: emptySubAgent(),
  isConnected: false,
  thinkingContent: "",
  askHumanQuestion: null,
  decidedApprovals: new Map(),

  addEvent: (event) => {
    set((state) => ({ events: [...state.events, event] }));
  },

  appendThinking: (content) =>
    set((state) => ({ thinkingContent: state.thinkingContent + content })),

  clearThinking: () => set({ thinkingContent: "" }),

  appendSubAgentThinking: (agent, content) =>
    set((state) => {
      const key =
        agent === "discovery"
          ? "discoveryAgentState"
          : agent === "kb"
            ? "kbAgentState"
            : "historyAgentState";
      return {
        [key]: {
          ...state[key],
          thinkingContent: state[key].thinkingContent + content,
        },
      };
    }),

  flushSubAgentThinking: (agent, timestamp) =>
    set((state) => {
      const key =
        agent === "discovery"
          ? "discoveryAgentState"
          : agent === "kb"
            ? "kbAgentState"
            : "historyAgentState";
      const agentState = state[key];
      if (!agentState.thinkingContent) return {};
      return {
        [key]: {
          events: [
            ...agentState.events,
            {
              event_type: "thinking",
              data: {
                content: agentState.thinkingContent,
                phase: agent === "discovery" ? "discover_project" : "gather_context",
                agent,
              },
              timestamp,
            },
          ],
          thinkingContent: "",
        },
      };
    }),

  addSubAgentEvent: (agent, event) =>
    set((state) => {
      const key =
        agent === "discovery"
          ? "discoveryAgentState"
          : agent === "kb"
            ? "kbAgentState"
            : "historyAgentState";
      return {
        [key]: {
          ...state[key],
          events: [...state[key].events, event],
        },
      };
    }),

  setAskHumanQuestion: (question) => set({ askHumanQuestion: question }),

  setApprovalDecided: (approvalId, decision) =>
    set((state) => {
      const next = new Map(state.decidedApprovals);
      next.set(approvalId, decision);
      return { decidedApprovals: next };
    }),

  setConnected: (connected) => set({ isConnected: connected }),

  reset: () =>
    set({
      events: [],
      discoveryAgentState: emptySubAgent(),
      historyAgentState: emptySubAgent(),
      kbAgentState: emptySubAgent(),
      isConnected: false,
      thinkingContent: "",
      askHumanQuestion: null,
      decidedApprovals: new Map(),
    }),
}));
