import { create } from "zustand";
import type { SSEEvent } from "@/lib/types";

export type PhaseStatus = "pending" | "active" | "completed";

export interface PhaseState {
  contextGathering: PhaseStatus;
  planning: PhaseStatus;
  investigation: PhaseStatus;
}

export interface EvaluationResult {
  outcome_type: string;
  verification_passed: boolean;
  confidence: string;
  evidence_summary: string;
  concerns: string[];
  recommendation: string;
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
  plannerPlanMd: string;
  plannerThinkingContent: string;
  evaluationResult: EvaluationResult | null;
  evaluatorThinkingContent: string;
  phaseState: PhaseState;
  isConnected: boolean;
  thinkingContent: string;
  answerContent: string;
  askHumanStreamContent: string;
  askHumanQuestion: string | null;
  isWaitingForAgent: boolean;
  resolutionConfirmRequired: boolean;
  resolutionConfirmResolved: boolean;
  decidedApprovals: Record<string, { decision: string; supplementText?: string }>;
  pendingSupplement: { approvalId: string } | null;
  scrollToBottomTrigger: number;
  addEvent: (event: SSEEvent) => void;
  setPlannerPlanMd: (md: string) => void;
  appendPlannerThinking: (content: string) => void;
  clearPlannerThinking: () => void;
  setEvaluationResult: (result: EvaluationResult | null) => void;
  appendEvaluatorThinking: (content: string) => void;
  clearEvaluatorThinking: () => void;
  appendThinking: (content: string) => void;
  clearThinking: () => void;
  appendAnswer: (content: string) => void;
  clearAnswer: () => void;
  appendAskHuman: (content: string) => void;
  clearAskHumanStream: () => void;
  appendSubAgentThinking: (agent: string, content: string) => void;
  flushSubAgentThinking: (agent: string, timestamp: string) => void;
  addSubAgentEvent: (agent: string, event: SSEEvent) => void;
  setSubAgentStatus: (agent: string, status: "idle" | "started" | "completed" | "failed") => void;
  updatePhase: (phase: string) => void;
  setAskHumanQuestion: (question: string | null) => void;
  setResolutionConfirmRequired: (required: boolean) => void;
  setWaitingForAgent: (waiting: boolean) => void;
  setResolutionConfirmResolved: (resolved: boolean) => void;
  setApprovalDecided: (approvalId: string, decision: string, supplementText?: string) => void;
  setPendingSupplement: (pending: { approvalId: string } | null) => void;
  triggerScrollToBottom: () => void;
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
  planning: "pending",
  investigation: "pending",
});

export const useIncidentStreamStore = create<IncidentStreamState>((set) => ({
  events: [],
  historyAgentState: emptySubAgent(),
  kbAgentState: emptySubAgent(),
  plannerPlanMd: "",
  plannerThinkingContent: "",
  evaluationResult: null,
  evaluatorThinkingContent: "",
  phaseState: initialPhaseState(),
  isConnected: false,
  isWaitingForAgent: false,
  thinkingContent: "",
  answerContent: "",
  askHumanStreamContent: "",
  askHumanQuestion: null,
  resolutionConfirmRequired: false,
  resolutionConfirmResolved: false,
  decidedApprovals: {},
  pendingSupplement: null,
  scrollToBottomTrigger: 0,

  addEvent: (event) => {
    set((state) => {
      // Dedup: if a real user_message arrives and an optimistic version exists, reconcile IDs
      if (event.event_type === "user_message" && event.event_id && !event.event_id.startsWith("optimistic-")) {
        const idx = state.events.findIndex(
          (e) =>
            e.event_type === "user_message" &&
            e.event_id?.startsWith("optimistic-") &&
            e.data.content === event.data.content
        );
        if (idx !== -1) {
          const newEvents = [...state.events];
          newEvents[idx] = { ...newEvents[idx], event_id: event.event_id };
          return { events: newEvents };
        }
      }
      return { events: [...state.events, event] };
    });
  },

  appendThinking: (content) =>
    set((state) => ({ thinkingContent: state.thinkingContent + content })),

  clearThinking: () => set({ thinkingContent: "" }),

  appendAnswer: (content) =>
    set((state) => ({ answerContent: state.answerContent + content })),

  clearAnswer: () => set({ answerContent: "" }),

  appendAskHuman: (content) =>
    set((state) => ({ askHumanStreamContent: state.askHumanStreamContent + content })),

  clearAskHumanStream: () => set({ askHumanStreamContent: "" }),

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

  setPlannerPlanMd: (md) => set({ plannerPlanMd: md, plannerThinkingContent: "" }),

  appendPlannerThinking: (content) =>
    set((state) => ({ plannerThinkingContent: state.plannerThinkingContent + content })),

  clearPlannerThinking: () => set({ plannerThinkingContent: "" }),

  setEvaluationResult: (result) => set({ evaluationResult: result, evaluatorThinkingContent: "" }),

  appendEvaluatorThinking: (content) =>
    set((state) => ({ evaluatorThinkingContent: state.evaluatorThinkingContent + content })),

  clearEvaluatorThinking: () => set({ evaluatorThinkingContent: "" }),

  updatePhase: (phase) =>
    set((state) => {
      const ps = { ...state.phaseState };
      if (phase === "gather_context") {
        if (ps.contextGathering === "pending") ps.contextGathering = "active";
      } else if (phase === "planning") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.planning === "pending") ps.planning = "active";
      } else if (phase === "investigation") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.planning === "active") ps.planning = "completed";
        if (ps.investigation === "pending") ps.investigation = "active";
      } else if (phase === "summary_complete") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.planning === "active") ps.planning = "completed";
        if (ps.investigation === "active") ps.investigation = "completed";
      }
      return { phaseState: ps };
    }),

  setAskHumanQuestion: (question) => set({ askHumanQuestion: question }),

  setWaitingForAgent: (waiting) => set({ isWaitingForAgent: waiting }),

  setResolutionConfirmRequired: (required) => set({ resolutionConfirmRequired: required }),

  setResolutionConfirmResolved: (resolved) => set({ resolutionConfirmResolved: resolved }),

  setApprovalDecided: (approvalId, decision, supplementText) =>
    set((state) => ({
      decidedApprovals: {
        ...state.decidedApprovals,
        [approvalId]: { decision, supplementText },
      },
    })),

  setPendingSupplement: (pending) => set({ pendingSupplement: pending }),

  triggerScrollToBottom: () =>
    set((state) => ({ scrollToBottomTrigger: state.scrollToBottomTrigger + 1 })),

  setConnected: (connected) => set({ isConnected: connected }),

  loadHistory: (events) => {
    const historyEvents: SSEEvent[] = [];
    const kbEvents: SSEEvent[] = [];
    const mainEvents: SSEEvent[] = [];
    const decided: Record<string, { decision: string; supplementText?: string }> = {};
    let askQuestion: string | null = null;
    let lastAskHumanIndex = -1;
    let hasUserMessageAfterAsk = false;
    let historyStatus: "idle" | "started" | "completed" | "failed" = "idle";
    let kbStatus: "idle" | "started" | "completed" | "failed" = "idle";
    let resolutionRequired = false;
    let resolutionResolved = false;
    let loadedPlanMd = "";
    let loadedEvalResult: EvaluationResult | null = null;

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      const phase = (event.data.phase as string) || "";
      const agent = (event.data.agent as string) || "";

      if (event.event_type === "approval_decided") {
        decided[event.data.approval_id as string] = {
          decision: event.data.decision as string,
          supplementText: event.data.supplement_text as string | undefined,
        };
        continue;
      }

      // agent_status → update sub-agent status, don't add to any event list
      if (event.event_type === "agent_status") {
        const status = event.data.status as "started" | "completed" | "failed";
        if (agent === "history") historyStatus = status;
        else if (agent === "kb") kbStatus = status;
        continue;
      }

      // thinking_done / answer_done / ask_human_done → DB boundary markers, skip in UI
      if (event.event_type === "thinking_done" || event.event_type === "answer_done" || event.event_type === "ask_human_done") {
        continue;
      }

      // plan_generated / plan_updated → track plan state
      if (event.event_type === "plan_generated" || event.event_type === "plan_updated") {
        loadedPlanMd = (event.data.plan_md as string) || "";
        continue;
      }

      // evaluation_completed → track evaluation result AND add to timeline
      if (event.event_type === "evaluation_completed") {
        loadedEvalResult = event.data.result as unknown as EvaluationResult;
        mainEvents.push(event);
        continue;
      }

      // evaluation_started → add to timeline (renders as inline card)
      if (event.event_type === "evaluation_started") {
        mainEvents.push(event);
        continue;
      }

      // planner_started → skip (no UI state needed)
      if (event.event_type === "planner_started") {
        continue;
      }

      // confirm_resolution_required → track state
      if (event.event_type === "confirm_resolution_required") {
        resolutionRequired = true;
        continue;
      }

      // resolution_confirmed → mark as resolved
      if (event.event_type === "resolution_confirmed") {
        resolutionResolved = true;
        continue;
      }

      if (event.event_type === "user_message" || event.event_type === "incident_stopped" || event.event_type === "skill_read" || event.event_type === "agent_interrupted") {
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
    const hasDone = mainEvents.some((e) => e.event_type === "done");
    const hasContext = historyEvents.length > 0 || kbEvents.length > 0;
    const hasMain = mainEvents.some((e) => e.event_type !== "done");
    const hasPlan = !!loadedPlanMd;
    const derivedPhase: PhaseState = {
      contextGathering: hasContext ? (hasPlan || hasMain || hasDone ? "completed" : "active") : "pending",
      planning: hasPlan ? (hasMain || hasDone ? "completed" : "active") : "pending",
      investigation: hasMain ? (hasDone ? "completed" : "active") : "pending",
    };

    set({
      events: mainEvents,
      historyAgentState: { events: historyEvents, thinkingContent: "", status: historyStatus },
      kbAgentState: { events: kbEvents, thinkingContent: "", status: kbStatus },
      plannerPlanMd: loadedPlanMd,
      evaluationResult: loadedEvalResult,
      phaseState: derivedPhase,
      decidedApprovals: decided,
      askHumanQuestion: askQuestion,
      isWaitingForAgent: false,
      resolutionConfirmRequired: resolutionRequired,
      resolutionConfirmResolved: resolutionResolved,
    });
  },

  reset: () =>
    set({
      events: [],
      historyAgentState: emptySubAgent(),
      kbAgentState: emptySubAgent(),
      plannerPlanMd: "",
      plannerThinkingContent: "",
      evaluationResult: null,
      evaluatorThinkingContent: "",
      phaseState: initialPhaseState(),
      isConnected: false,
      isWaitingForAgent: false,
      thinkingContent: "",
      answerContent: "",
      askHumanStreamContent: "",
      askHumanQuestion: null,
      resolutionConfirmRequired: false,
      resolutionConfirmResolved: false,
      decidedApprovals: {},
      pendingSupplement: null,
      scrollToBottomTrigger: 0,
    }),
}));
