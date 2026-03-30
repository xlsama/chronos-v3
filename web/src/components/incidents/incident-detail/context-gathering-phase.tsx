import { useMemo } from "react";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { cn, formatDuration } from "@/lib/utils";
import { PhaseSection } from "./phase-section";
import { SubAgentCard } from "./sub-agent-card";

interface ContextGatheringPhaseProps {
  isActiveIncident: boolean;
  isLast: boolean;
}

export function ContextGatheringPhase({ isActiveIncident, isLast }: ContextGatheringPhaseProps) {
  const historyAgentState = useIncidentStreamStore((s) => s.historyAgentState);
  const kbAgentState = useIncidentStreamStore((s) => s.kbAgentState);
  const phaseState = useIncidentStreamStore((s) => s.phaseState);

  const contextActive = phaseState.contextGathering === "active";

  const hasHistory =
    contextActive ||
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent ||
    historyAgentState.status !== "idle";
  const hasKB =
    contextActive ||
    kbAgentState.events.length > 0 ||
    !!kbAgentState.thinkingContent ||
    kbAgentState.status !== "idle";
  const hasGatherContext = hasHistory || hasKB;

  const hasSubAgentContent =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent ||
    kbAgentState.events.length > 0 ||
    !!kbAgentState.thinkingContent;

  const shouldUseFixedContextLayout = contextActive && hasGatherContext && hasSubAgentContent;

  const contextSubtitle = useMemo(() => {
    const allContextEvents = [...historyAgentState.events, ...kbAgentState.events];
    if (allContextEvents.length < 2) return "";
    const sorted = allContextEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const dur = formatDuration(sorted[0].timestamp, sorted[sorted.length - 1].timestamp);
    return dur !== "0s" ? dur : "";
  }, [historyAgentState.events, kbAgentState.events]);

  return (
    <PhaseSection
      title="上下文收集"
      subtitle={contextSubtitle}
      status={phaseState.contextGathering}
      defaultExpanded={phaseState.investigation === "pending" || undefined}
      isLast={isLast}
      contentClassName={cn(
        shouldUseFixedContextLayout && [
          "overflow-hidden",
          "has-[[data-expanded]]:h-[calc(100dvh-19rem)]",
          "has-[[data-expanded]]:min-h-[18rem]",
          "has-[[data-expanded]]:md:h-[calc(100dvh-17rem)]",
        ],
      )}
    >
      <div
        className={cn(
          "min-h-0",
          shouldUseFixedContextLayout
            ? "flex flex-col gap-3 has-[[data-expanded]]:h-full"
            : "space-y-3",
        )}
        data-testid="context-subagent-layout"
      >
        {(hasHistory || isActiveIncident) && (
          <SubAgentCard
            agentName="history"
            events={historyAgentState.events}
            status={historyAgentState.status}
            streamingContent={historyAgentState.thinkingContent}
            forceExpanded={phaseState.contextGathering === "active"}
            fixedLayout={shouldUseFixedContextLayout}
          />
        )}
        {(hasKB || isActiveIncident) && (
          <SubAgentCard
            agentName="kb"
            events={kbAgentState.events}
            status={kbAgentState.status}
            streamingContent={kbAgentState.thinkingContent}
            forceExpanded={phaseState.contextGathering === "active"}
            fixedLayout={shouldUseFixedContextLayout}
          />
        )}
      </div>
    </PhaseSection>
  );
}
