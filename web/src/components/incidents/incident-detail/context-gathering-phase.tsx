import { useMemo } from "react";
import { MessageCircleQuestion } from "lucide-react";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { cn, formatDuration } from "@/lib/utils";
import { PhaseSection } from "./phase-section";
import { AgentCard } from "./agent-card";
import { UserMessageBubble } from "./user-message-bubble";
import { Markdown } from "@/components/ui/markdown";
import { TextDotsLoader } from "@/components/ui/text-dots-loader";
import type { SSEEvent } from "@/lib/types";

interface ContextGatheringPhaseProps {
  isActiveIncident: boolean;
  isLast: boolean;
}

export function ContextGatheringPhase({ isActiveIncident, isLast }: ContextGatheringPhaseProps) {
  const historyAgentState = useIncidentStreamStore((s) => s.historyAgentState);
  const kbAgentState = useIncidentStreamStore((s) => s.kbAgentState);
  const phaseState = useIncidentStreamStore((s) => s.phaseState);
  const triageEvents = useIncidentStreamStore((s) => s.triageEvents);
  const askHumanStreamContent = useIncidentStreamStore((s) => s.askHumanStreamContent);
  const askHumanPhase = useIncidentStreamStore((s) => s.askHumanPhase);
  const isWaitingForAgent = useIncidentStreamStore((s) => s.isWaitingForAgent);

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

  const hasAgentContent =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent ||
    kbAgentState.events.length > 0 ||
    !!kbAgentState.thinkingContent;

  const hasTriageContent =
    triageEvents.length > 0 ||
    (askHumanPhase === "gather_context" && !!askHumanStreamContent);

  const shouldUseFixedContextLayout = contextActive && hasGatherContext && hasAgentContent && !hasTriageContent;

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
        data-testid="context-agent-layout"
      >
        {(hasHistory || isActiveIncident) && (
          <AgentCard
            agentName="history"
            events={historyAgentState.events}
            status={historyAgentState.status}
            streamingContent={historyAgentState.thinkingContent}
            forceExpanded={phaseState.contextGathering === "active"}
            fixedLayout={shouldUseFixedContextLayout}
          />
        )}
        {(hasKB || isActiveIncident) && (
          <AgentCard
            agentName="kb"
            events={kbAgentState.events}
            status={kbAgentState.status}
            streamingContent={kbAgentState.thinkingContent}
            forceExpanded={phaseState.contextGathering === "active"}
            fixedLayout={shouldUseFixedContextLayout}
          />
        )}
        {hasTriageContent && (
          <TriageSection
            triageEvents={triageEvents}
            askHumanStreamContent={askHumanStreamContent}
            askHumanPhase={askHumanPhase}
            isWaitingForAgent={isWaitingForAgent}
          />
        )}
      </div>
    </PhaseSection>
  );
}

function TriageSection({
  triageEvents,
  askHumanStreamContent,
  askHumanPhase,
  isWaitingForAgent,
}: {
  triageEvents: SSEEvent[];
  askHumanStreamContent: string;
  askHumanPhase: string | null;
  isWaitingForAgent: boolean;
}) {
  const isLiveStreaming = askHumanPhase === "gather_context" && !!askHumanStreamContent;
  const showWaiting = isWaitingForAgent && askHumanPhase === "gather_context" && !askHumanStreamContent;

  return (
    <div className="space-y-3">
      {triageEvents.map((event, i) => {
        if (event.event_type === "ask_human") {
          return (
            <div key={i} className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
              <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
              <div>
                <p className="text-sm font-medium text-amber-800 dark:text-amber-200">Agent 需要更多信息</p>
                <Markdown
                  content={event.data.question as string}
                  variant="compact"
                  className="mt-1 card-markdown card-markdown--amber"
                />
              </div>
            </div>
          );
        }
        if (event.event_type === "user_message") {
          return (
            <UserMessageBubble
              key={i}
              content={event.data.content as string}
              attachments={event.data.attachments as { content_type: string; bytes: string }[] | undefined}
              attachment_ids={event.data.attachment_ids as string[] | undefined}
              attachments_meta={event.data.attachments_meta as { id: string; filename: string; content_type: string; size: number }[] | undefined}
            />
          );
        }
        return null;
      })}
      {isLiveStreaming && (
        <div className="animate-in fade-in duration-150">
          <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
            <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div>
              <p className="text-sm font-medium text-amber-800 dark:text-amber-200">Agent 需要更多信息</p>
              <Markdown
                content={askHumanStreamContent}
                streaming
                variant="compact"
                className="mt-1 card-markdown card-markdown--amber"
              />
            </div>
          </div>
        </div>
      )}
      {showWaiting && (
        <div className="animate-in fade-in duration-150 px-1 py-2">
          <TextDotsLoader text="Agent 思考中" size="sm" />
        </div>
      )}
    </div>
  );
}
