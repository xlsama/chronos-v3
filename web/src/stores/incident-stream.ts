import { create } from "zustand";
import type { SSEEvent } from "@/lib/types";

export type PhaseStatus = "pending" | "active" | "completed";

export interface PhaseState {
  contextGathering: PhaseStatus;
  planning: PhaseStatus;
  investigation: PhaseStatus;
  evaluation: PhaseStatus;
}

export interface InvestigationPlan {
  symptom_category: string;
  target_scope: string;
  hypotheses: {
    id: string;
    description: string;
    status: "pending" | "investigating" | "confirmed" | "eliminated";
    priority: number;
    observation_surfaces: string[];
    evidence_for: string[];
    evidence_against: string[];
  }[];
  null_hypothesis: string | null;
  current_phase: string;
  next_action: string;
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
  plannerPlan: InvestigationPlan | null;
  evaluationResult: EvaluationResult | null;
  phaseState: PhaseState;
  isConnected: boolean;
  thinkingContent: string;
  answerContent: string;
  askHumanStreamContent: string;
  askHumanQuestion: string | null;
  isWaitingForAgent: boolean;
  resolutionConfirmRequired: boolean;
  resolutionConfirmResolved: boolean;
  decidedApprovals: Record<string, string>;
  pendingSupplement: { approvalId: string } | null;
  scrollToBottomTrigger: number;
  addEvent: (event: SSEEvent) => void;
  setPlannerPlan: (plan: InvestigationPlan) => void;
  setEvaluationResult: (result: EvaluationResult | null) => void;
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
  setApprovalDecided: (approvalId: string, decision: string) => void;
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
  evaluation: "pending",
});

export const useIncidentStreamStore = create<IncidentStreamState>((set) => ({
  events: [],
  historyAgentState: emptySubAgent(),
  kbAgentState: emptySubAgent(),
  plannerPlan: null,
  evaluationResult: null,
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

  setPlannerPlan: (plan) => set({ plannerPlan: plan }),

  setEvaluationResult: (result) => set({ evaluationResult: result }),

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
      } else if (phase === "evaluation") {
        if (ps.investigation === "active") ps.investigation = "completed";
        if (ps.evaluation === "pending") ps.evaluation = "active";
      } else if (phase === "summary_complete") {
        if (ps.contextGathering === "active") ps.contextGathering = "completed";
        if (ps.planning === "active") ps.planning = "completed";
        if (ps.investigation === "active") ps.investigation = "completed";
        if (ps.evaluation === "active") ps.evaluation = "completed";
      }
      return { phaseState: ps };
    }),

  setAskHumanQuestion: (question) => set({ askHumanQuestion: question }),

  setWaitingForAgent: (waiting) => set({ isWaitingForAgent: waiting }),

  setResolutionConfirmRequired: (required) => set({ resolutionConfirmRequired: required }),

  setResolutionConfirmResolved: (resolved) => set({ resolutionConfirmResolved: resolved }),

  setApprovalDecided: (approvalId, decision) =>
    set((state) => ({
      decidedApprovals: { ...state.decidedApprovals, [approvalId]: decision },
    })),

  setPendingSupplement: (pending) => set({ pendingSupplement: pending }),

  triggerScrollToBottom: () =>
    set((state) => ({ scrollToBottomTrigger: state.scrollToBottomTrigger + 1 })),

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
    let resolutionRequired = false;
    let resolutionResolved = false;
    let loadedPlan: InvestigationPlan | null = null;
    let loadedEvalResult: EvaluationResult | null = null;

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

      // thinking_done / answer_done / ask_human_done → DB boundary markers, skip in UI
      if (event.event_type === "thinking_done" || event.event_type === "answer_done" || event.event_type === "ask_human_done") {
        continue;
      }

      // plan_generated / plan_updated → track plan state
      if (event.event_type === "plan_generated" || event.event_type === "plan_updated") {
        loadedPlan = event.data.plan as unknown as InvestigationPlan;
        continue;
      }

      // evaluation_completed → track evaluation result
      if (event.event_type === "evaluation_completed") {
        loadedEvalResult = event.data.result as unknown as EvaluationResult;
        continue;
      }

      // evaluation_started → skip (no UI state needed)
      if (event.event_type === "evaluation_started") {
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
    const hasPlan = loadedPlan !== null;
    const hasEval = loadedEvalResult !== null;

    const derivedPhase: PhaseState = {
      contextGathering: hasContext ? (hasPlan || hasMain || hasDone ? "completed" : "active") : "pending",
      planning: hasPlan ? (hasMain || hasDone ? "completed" : "active") : "pending",
      investigation: hasMain ? (hasEval || hasDone ? "completed" : "active") : "pending",
      evaluation: hasEval ? "completed" : "pending",
    };

    set({
      events: mainEvents,
      historyAgentState: { events: historyEvents, thinkingContent: "", status: historyStatus },
      kbAgentState: { events: kbEvents, thinkingContent: "", status: kbStatus },
      plannerPlan: loadedPlan,
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
      plannerPlan: null,
      evaluationResult: null,
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
