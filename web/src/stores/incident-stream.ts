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
  status: "idle" | "started" | "completed" | "failed";
}

interface IncidentStreamState {
  events: SSEEvent[];
  historyAgentState: SubAgentState;
  kbAgentState: SubAgentState;
  phaseState: PhaseState;
  isConnected: boolean;
  thinkingContent: string;
  answerContent: string;
  reportStreamContent: string;
  askHumanQuestion: string | null;
  decidedApprovals: Record<string, string>;
  addEvent: (event: SSEEvent) => void;
  appendThinking: (content: string) => void;
  clearThinking: () => void;
  appendAnswer: (content: string) => void;
  clearAnswer: () => void;
  appendReportStream: (content: string) => void;
  clearReportStream: () => void;
  appendSubAgentThinking: (agent: string, content: string) => void;
  flushSubAgentThinking: (agent: string, timestamp: string) => void;
  addSubAgentEvent: (agent: string, event: SSEEvent) => void;
  setSubAgentStatus: (agent: string, status: "idle" | "started" | "completed" | "failed") => void;
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
  status: "idle",
});

const initialPhaseState = (): PhaseState => ({
  contextGathering: "pending",
  investigation: "pending",
  report: "pending",
});

export const useIncidentStreamStore = create<IncidentStreamState>((set) => ({
  events: [],
  historyAgentState: emptySubAgent(),
  kbAgentState: emptySubAgent(),
  phaseState: initialPhaseState(),
  isConnected: false,
  thinkingContent: "",
  answerContent: "",
  reportStreamContent: "",
  askHumanQuestion: null,
  decidedApprovals: {},

  addEvent: (event) => {
    set((state) => ({ events: [...state.events, event] }));
  },

  appendThinking: (content) =>
    set((state) => ({ thinkingContent: state.thinkingContent + content })),

  clearThinking: () => set({ thinkingContent: "" }),

  appendAnswer: (content) =>
    set((state) => ({ answerContent: state.answerContent + content })),

  clearAnswer: () => set({ answerContent: "" }),

  appendReportStream: (content) =>
    set((state) => {
      const ps = { ...state.phaseState };
      if (ps.investigation === "active") ps.investigation = "completed";
      if (ps.report !== "active") ps.report = "active";
      return {
        reportStreamContent: state.reportStreamContent + content,
        phaseState: ps,
      };
    }),

  clearReportStream: () => set({ reportStreamContent: "" }),

  appendSubAgentThinking: (agent, content) =>
    set((state) => {
      const key = agent === "kb" ? "kbAgentState" : "historyAgentState";
      return {
        [key]: {
          ...state[key],
          thinkingContent: state[key].thinkingContent + content,
        },
      };
    }),

  flushSubAgentThinking: (agent, timestamp) =>
    set((state) => {
      const key = agent === "kb" ? "kbAgentState" : "historyAgentState";
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
                phase: "gather_context",
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
      const key = agent === "kb" ? "kbAgentState" : "historyAgentState";
      return {
        [key]: {
          ...state[key],
          events: [...state[key].events, event],
        },
      };
    }),

  setSubAgentStatus: (agent, status) =>
    set((state) => {
      const key = agent === "kb" ? "kbAgentState" : "historyAgentState";
      return {
        [key]: {
          ...state[key],
          status,
        },
      };
    }),

  updatePhase: (phase) =>
    set((state) => {
      const ps = { ...state.phaseState };
      if (phase === "gather_context") {
        if (ps.contextGathering === "pending") ps.contextGathering = "active";
      } else if (phase === "main") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.investigation === "pending") ps.investigation = "active";
      } else if (phase === "summarize") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.investigation === "active") ps.investigation = "completed";
        if (ps.report === "pending") ps.report = "active";
      } else if (phase === "summary_complete") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.investigation === "active") ps.investigation = "completed";
        ps.report = "completed";
      }
      return { phaseState: ps };
    }),

  setAskHumanQuestion: (question) => set({ askHumanQuestion: question }),

  setApprovalDecided: (approvalId, decision) =>
    set((state) => ({
      decidedApprovals: { ...state.decidedApprovals, [approvalId]: decision },
    })),

  setConnected: (connected) => set({ isConnected: connected }),

  loadHistory: (events) => {
    const historyEvents: SSEEvent[] = [];
    const kbEvents: SSEEvent[] = [];
    const mainEvents: SSEEvent[] = [];
    const decided: Record<string, string> = {};
    let askQuestion: string | null = null;
    let lastAskHumanIndex = -1;
    let hasUserMessageAfterAsk = false;
    let historyStatus: "idle" | "started" | "completed" | "failed" = "idle";
    let kbStatus: "idle" | "started" | "completed" | "failed" = "idle";

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      const phase = (event.data.phase as string) || "";
      const agent = (event.data.agent as string) || "";

      if (event.event_type === "approval_decided") {
        decided[event.data.approval_id as string] =
          event.data.decision as string;
        continue;
      }

      // agent_status → update sub-agent status, don't add to any event list
      if (event.event_type === "agent_status") {
        const status = event.data.status as "started" | "completed" | "failed";
        if (agent === "history") historyStatus = status;
        else if (agent === "kb") kbStatus = status;
        continue;
      }

      // thinking_done / answer_done → DB boundary markers, skip in UI
      if (event.event_type === "thinking_done" || event.event_type === "answer_done") {
        continue;
      }

      if (event.event_type === "user_message" || event.event_type === "incident_stopped" || event.event_type === "skill_used") {
        if (lastAskHumanIndex >= 0) hasUserMessageAfterAsk = true;
        mainEvents.push(event);
        continue;
      }

      // answer → directly add to mainEvents
      if (event.event_type === "answer") {
        mainEvents.push(event);
        continue;
      }

      if (phase === "gather_context") {
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
    const hasContext = historyEvents.length > 0 || kbEvents.length > 0;
    const hasMain = mainEvents.some((e) => e.event_type !== "summary" && e.event_type !== "ask_human" && e.event_type !== "answer");
    const hasSummary = mainEvents.some((e) => e.event_type === "summary");

    const derivedPhase: PhaseState = {
      contextGathering: hasContext ? (hasMain || hasSummary ? "completed" : "active") : "pending",
      investigation: hasMain ? (hasSummary ? "completed" : "active") : "pending",
      report: hasSummary ? "completed" : "pending",
    };

    set({
      events: mainEvents,
      historyAgentState: { events: historyEvents, thinkingContent: "", status: historyStatus },
      kbAgentState: { events: kbEvents, thinkingContent: "", status: kbStatus },
      phaseState: derivedPhase,
      decidedApprovals: decided,
      askHumanQuestion: askQuestion,
    });
  },

  reset: () =>
    set({
      events: [],
      historyAgentState: emptySubAgent(),
      kbAgentState: emptySubAgent(),
      phaseState: initialPhaseState(),
      isConnected: false,
      thinkingContent: "",
      answerContent: "",
      reportStreamContent: "",
      askHumanQuestion: null,
      decidedApprovals: {},
    }),
}));
