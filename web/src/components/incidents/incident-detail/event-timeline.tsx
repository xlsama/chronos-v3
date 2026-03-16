import { useIncidentStreamStore } from "@/stores/incident-stream";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { ApprovalCard } from "./approval-card";
import { SummarySection } from "./summary-section";
import { SubAgentCard } from "./sub-agent-card";
import { MessageCircleQuestion } from "lucide-react";

interface EventTimelineProps {
  incidentId?: string;
  savedToMemory?: boolean;
}

export function EventTimeline({ incidentId, savedToMemory }: EventTimelineProps) {
  const {
    events,
    historyAgentState,
    kbAgentState,
    thinkingContent,
  } = useIncidentStreamStore();

  const hasHistory =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent;
  const hasKB =
    kbAgentState.events.length > 0 || !!kbAgentState.thinkingContent;
  const hasGatherContext = hasHistory || hasKB;

  return (
    <div className="space-y-3 p-4" data-testid="event-timeline">
      {/* Gather Context Phase — sub agent cards in grid */}
      {hasGatherContext && (
        <div className="grid gap-3 sm:grid-cols-2">
          {hasHistory && (
            <SubAgentCard
              agentName="history"
              events={historyAgentState.events}
              isStreaming={!!historyAgentState.thinkingContent}
              streamingContent={historyAgentState.thinkingContent}
            />
          )}
          {hasKB && (
            <SubAgentCard
              agentName="kb"
              events={kbAgentState.events}
              isStreaming={!!kbAgentState.thinkingContent}
              streamingContent={kbAgentState.thinkingContent}
            />
          )}
        </div>
      )}

      {/* Main Agent Events */}
      {events.map((event, i) => {
        switch (event.event_type) {
          case "thinking":
            return (
              <ThinkingBubble
                key={i}
                content={event.data.content as string}
              />
            );
          case "tool_call":
            return (
              <ToolCallCard
                key={i}
                name={event.data.name as string}
                args={event.data.args as Record<string, unknown>}
              />
            );
          case "tool_result":
            return (
              <ToolCallCard
                key={i}
                name={event.data.name as string}
                output={event.data.output as string}
                isResult
              />
            );
          case "approval_required":
            return (
              <ApprovalCard
                key={i}
                toolCall={event.data.tool_args as Record<string, unknown>}
                approvalId={event.data.approval_id as string}
              />
            );
          case "ask_human":
            return (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4"
              >
                <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                <div>
                  <p className="text-sm font-medium text-amber-800">
                    Agent 需要更多信息
                  </p>
                  <p className="mt-1 text-sm text-amber-700">
                    {event.data.question as string}
                  </p>
                </div>
              </div>
            );
          case "summary":
            return (
              <SummarySection
                key={i}
                markdown={event.data.summary_md as string}
                incidentId={incidentId}
                savedToMemory={savedToMemory}
              />
            );
          case "error":
            return (
              <div
                key={i}
                className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
              >
                Error: {event.data.message as string}
              </div>
            );
          default:
            return null;
        }
      })}

      {/* Live thinking stream */}
      {thinkingContent && (
        <ThinkingBubble content={thinkingContent} isStreaming />
      )}
    </div>
  );
}
