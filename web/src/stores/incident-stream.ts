import { create } from "zustand";
import type { SSEEvent } from "@/lib/types";

export type PhaseStatus = "pending" | "active" | "completed";

export interface PhaseState {
  contextGathering: PhaseStatus;
  investigation: PhaseStatus;
  report: PhaseStatus;
}

interface SubAgentState {
  events: SSEEvent[];
  thinkingContent: string;
}

interface IncidentStreamState {
  events: SSEEvent[];
  discoveryAgentState: SubAgentState;
  historyAgentState: SubAgentState;
  kbAgentState: SubAgentState;
  phaseState: PhaseState;
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
  updatePhase: (phase: string) => void;
  setAskHumanQuestion: (question: string | null) => void;
  setApprovalDecided: (approvalId: string, decision: string) => void;
  setConnected: (connected: boolean) => void;
  loadHistory: (events: SSEEvent[]) => void;
  reset: () => void;
}

const emptySubAgent = (): SubAgentState => ({
  events: [],
  thinkingContent: "",
});

const initialPhaseState = (): PhaseState => ({
  contextGathering: "pending",
  investigation: "pending",
  report: "pending",
});

export const useIncidentStreamStore = create<IncidentStreamState>((set) => ({
  events: [],
  discoveryAgentState: emptySubAgent(),
  historyAgentState: emptySubAgent(),
  kbAgentState: emptySubAgent(),
  phaseState: initialPhaseState(),
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

  updatePhase: (phase) =>
    set((state) => {
      const ps = { ...state.phaseState };
      if (phase === "gather_context" || phase === "discover_project") {
        if (ps.contextGathering === "pending") ps.contextGathering = "active";
      } else if (phase === "main") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.investigation === "pending") ps.investigation = "active";
      } else if (phase === "summarize") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.investigation === "active") ps.investigation = "completed";
        ps.report = "completed";
      }
      return { phaseState: ps };
    }),

  setAskHumanQuestion: (question) => set({ askHumanQuestion: question }),

  setApprovalDecided: (approvalId, decision) =>
    set((state) => {
      const next = new Map(state.decidedApprovals);
      next.set(approvalId, decision);
      return { decidedApprovals: next };
    }),

  setConnected: (connected) => set({ isConnected: connected }),

  loadHistory: (events) => {
    const discoveryEvents: SSEEvent[] = [];
    const historyEvents: SSEEvent[] = [];
    const kbEvents: SSEEvent[] = [];
    const mainEvents: SSEEvent[] = [];
    const decided = new Map<string, string>();
    let askQuestion: string | null = null;
    let lastAskHumanIndex = -1;
    let hasUserMessageAfterAsk = false;

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      const phase = (event.data.phase as string) || "";
      const agent = (event.data.agent as string) || "";

      if (event.event_type === "approval_decided") {
        decided.set(
          event.data.approval_id as string,
          event.data.decision as string,
        );
        continue;
      }

      if (event.event_type === "user_message") {
        if (lastAskHumanIndex >= 0) hasUserMessageAfterAsk = true;
        continue;
      }

      if (phase === "discover_project") {
        discoveryEvents.push(event);
      } else if (phase === "gather_context") {
        if (agent === "kb") {
          kbEvents.push(event);
        } else if (agent === "history") {
          historyEvents.push(event);
        } else {
          mainEvents.push(event);
        }
      } else {
        if (event.event_type === "ask_human") {
          lastAskHumanIndex = i;
          hasUserMessageAfterAsk = false;
        }
        mainEvents.push(event);
      }
    }

    // Restore askHumanQuestion if last ask_human has no subsequent user_message
    if (lastAskHumanIndex >= 0 && !hasUserMessageAfterAsk) {
      const askEvent = events[lastAskHumanIndex];
      askQuestion = (askEvent.data.question as string) || null;
    }

    // Derive phase state from loaded events
    const hasContext = discoveryEvents.length > 0 || historyEvents.length > 0 || kbEvents.length > 0;
    const hasMain = mainEvents.some((e) => e.event_type !== "summary" && e.event_type !== "ask_human");
    const hasSummary = mainEvents.some((e) => e.event_type === "summary");

    const derivedPhase: PhaseState = {
      contextGathering: hasContext ? (hasMain || hasSummary ? "completed" : "active") : "pending",
      investigation: hasMain ? (hasSummary ? "completed" : "active") : "pending",
      report: hasSummary ? "completed" : "pending",
    };

    set({
      events: mainEvents,
      discoveryAgentState: { events: discoveryEvents, thinkingContent: "" },
      historyAgentState: { events: historyEvents, thinkingContent: "" },
      kbAgentState: { events: kbEvents, thinkingContent: "" },
      phaseState: derivedPhase,
      decidedApprovals: decided,
      askHumanQuestion: askQuestion,
    });
  },

  reset: () =>
    set({
      events: [],
      discoveryAgentState: emptySubAgent(),
      historyAgentState: emptySubAgent(),
      kbAgentState: emptySubAgent(),
      phaseState: initialPhaseState(),
      isConnected: false,
      thinkingContent: "",
      askHumanQuestion: null,
      decidedApprovals: new Map(),
    }),
}));
