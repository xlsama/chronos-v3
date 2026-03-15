import { useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import type { SSEEvent } from "@/lib/types";

interface SubAgentCardProps {
  agentName: string;
  events: SSEEvent[];
  isStreaming?: boolean;
  streamingContent?: string;
}

export function SubAgentCard({
  agentName,
  events,
  isStreaming,
  streamingContent,
}: SubAgentCardProps) {
  const [expanded, setExpanded] = useState(false);

  const hasEvents = events.length > 0 || !!streamingContent;
  const status = isStreaming ? "检索中..." : "完成";

  return (
    <div
      className="rounded-lg border border-blue-200 bg-blue-50/50 p-3"
      data-testid="sub-agent-card"
    >
      <button
        className="flex w-full items-center gap-2 text-left text-sm font-medium text-blue-800"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <Search className="h-4 w-4" />
        <span>
          {agentName === "history" ? "历史事件检索" : agentName}
        </span>
        <span className="ml-auto text-xs text-blue-600">{status}</span>
      </button>

      {expanded && hasEvents && (
        <div className="mt-2 space-y-2 pl-6 text-sm text-blue-900/80">
          {events.map((event, i) => {
            if (event.event_type === "thinking") {
              return (
                <div key={i} className="whitespace-pre-wrap text-xs opacity-80">
                  {event.data.content as string}
                </div>
              );
            }
            if (event.event_type === "tool_call") {
              return (
                <div
                  key={i}
                  className="rounded border border-blue-200 bg-white/60 p-2 text-xs"
                >
                  <span className="font-mono font-semibold">
                    {event.data.name as string}
                  </span>
                  <pre className="mt-1 overflow-auto text-xs opacity-70">
                    {JSON.stringify(event.data.args, null, 2)}
                  </pre>
                </div>
              );
            }
            if (event.event_type === "tool_result") {
              return (
                <div
                  key={i}
                  className="rounded border border-blue-200 bg-white/60 p-2 text-xs"
                >
                  <span className="font-mono font-semibold">
                    {event.data.name as string} 结果
                  </span>
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs opacity-70">
                    {event.data.output as string}
                  </pre>
                </div>
              );
            }
            return null;
          })}

          {isStreaming && streamingContent && (
            <div className="whitespace-pre-wrap text-xs opacity-80 animate-pulse">
              {streamingContent}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
