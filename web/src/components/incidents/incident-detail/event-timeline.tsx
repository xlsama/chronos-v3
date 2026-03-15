import { useIncidentStreamStore } from "@/stores/incident-stream";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { ApprovalCard } from "./approval-card";
import { SummarySection } from "./summary-section";

export function EventTimeline() {
  const { events, thinkingContent } = useIncidentStreamStore();

  return (
    <div className="space-y-3 p-4">
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
                toolCall={
                  event.data.pending_tool_call as Record<string, unknown>
                }
              />
            );
          case "summary":
            return (
              <SummarySection
                key={i}
                markdown={event.data.summary_md as string}
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
