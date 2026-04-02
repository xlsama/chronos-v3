import { useIncidentStreamStore } from "@/stores/incident-stream";
import { PhaseSection } from "./phase-section";
import { PlanContent } from "./plan-phase-section";
import { ContextGatheringPhase } from "./context-gathering-phase";
import { InvestigationPhase } from "./investigation-phase";
import { VerificationPhase } from "./verification-phase";

interface EventTimelineProps {
  incidentId: string;
  incidentStatus?: string;
  scrollParent?: HTMLDivElement | null;
}

export function EventTimeline({ incidentId, incidentStatus, scrollParent }: EventTimelineProps) {
  const phaseState = useIncidentStreamStore((s) => s.phaseState);
  const planMd = useIncidentStreamStore((s) => s.planMd);
  const hasEvents = useIncidentStreamStore((s) => s.events.length > 0);
  const hasThinking = useIncidentStreamStore((s) => !!s.thinkingContent);
  const hasAnswerStream = useIncidentStreamStore((s) => !!s.answerContent);
  const hasAskHumanStream = useIncidentStreamStore((s) => !!s.askHumanStreamContent);
  const hasInvestigations = useIncidentStreamStore((s) => s.investigations.length > 0);
  const hasContextHistory = useIncidentStreamStore(
    (s) => s.historyAgentState.events.length > 0 || !!s.historyAgentState.thinkingContent || s.historyAgentState.status !== "idle",
  );
  const hasContextKB = useIncidentStreamStore(
    (s) => s.kbAgentState.events.length > 0 || !!s.kbAgentState.thinkingContent || s.kbAgentState.status !== "idle",
  );
  const hasTriageContent = useIncidentStreamStore((s) => s.triageEvents.length > 0);
  const bothAgentsDone = useIncidentStreamStore((s) => {
    const h = s.historyAgentState.status;
    const k = s.kbAgentState.status;
    const hDone = h === "completed" || h === "failed" || h === "idle";
    const kDone = k === "completed" || k === "failed" || k === "idle";
    return hDone && kDone && (h !== "idle" || k !== "idle");
  });

  const isActiveIncident =
    incidentStatus === "open" ||
    incidentStatus === "investigating" ||
    incidentStatus === "interrupted";

  const contextActive = phaseState.contextGathering === "active";
  const hasGatherContext = contextActive || hasContextHistory || hasContextKB;
  const hasInvestigation = hasEvents || hasThinking || hasAnswerStream || hasAskHumanStream || hasInvestigations;

  const isTransitioningToInvestigation =
    isActiveIncident &&
    phaseState.contextGathering === "active" &&
    phaseState.investigation === "pending" &&
    bothAgentsDone;

  const isTransitioningFromPlanning =
    isActiveIncident &&
    phaseState.planning === "active" &&
    phaseState.investigation === "pending" &&
    !!planMd;

  const hasVerification = useIncidentStreamStore(
    (s) => s.investigations.some((i) => i.hypothesisId === "VERIFY"),
  );

  // Phase visibility
  const showContextGathering =
    hasGatherContext || hasTriageContent || phaseState.contextGathering !== "pending" || isActiveIncident;
  const showPlanning = !!planMd || phaseState.planning !== "pending";
  const showInvestigation =
    hasInvestigation || phaseState.investigation !== "pending" || isTransitioningToInvestigation || isTransitioningFromPlanning;
  const showVerification = hasVerification || phaseState.verification !== "pending";

  return (
    <div className="px-8 py-4" data-testid="event-timeline">
      {/* Phase 1: Context Gathering */}
      {showContextGathering && (
        <ContextGatheringPhase
          isActiveIncident={isActiveIncident}
          isLast={!showPlanning && !showInvestigation}
        />
      )}

      {/* Phase 2: Planning */}
      {showPlanning && (
        <PhaseSection
          title="制定计划"
          status={phaseState.planning}
          isLast={!showInvestigation}
        >
          <PlanContent />
        </PhaseSection>
      )}

      {/* Phase 3: Investigation */}
      {showInvestigation && (
        <PhaseSection
          title="排查处置"
          status={(isTransitioningToInvestigation || isTransitioningFromPlanning) ? "active" : phaseState.investigation}
          defaultExpanded
          isLast={!showVerification}
        >
          <InvestigationPhase
            incidentId={incidentId}
            incidentStatus={incidentStatus}
            scrollParent={scrollParent}
            isTransitioning={isTransitioningToInvestigation || isTransitioningFromPlanning}
          />
        </PhaseSection>
      )}

      {/* Phase 4: Verification */}
      {showVerification && (
        <PhaseSection
          title="验证修复"
          status={phaseState.verification}
          defaultExpanded
          isLast
        >
          <VerificationPhase incidentId={incidentId} incidentStatus={incidentStatus} />
        </PhaseSection>
      )}
    </div>
  );
}
