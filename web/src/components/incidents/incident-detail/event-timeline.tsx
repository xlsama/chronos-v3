import { useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Search, Brain, FileText, MessageCircleQuestion } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { getConnections } from "@/api/connections";
import { formatRelativeTime, formatDuration } from "@/lib/utils";
import type { SSEEvent } from "@/lib/types";
import { PhaseSection } from "./phase-section";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { ApprovalCard } from "./approval-card";
import { SummarySection } from "./summary-section";
import { SubAgentCard } from "./sub-agent-card";
import { UserMessageBubble } from "./user-message-bubble";

interface EventTimelineProps {
  incidentId?: string;
  savedToMemory?: boolean;
  summaryMarkdown?: string | null;
}

type TimelineItem =
  | { type: "thinking"; event: SSEEvent }
  | { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent }
  | { type: "approval_required"; event: SSEEvent }
  | { type: "ask_human"; event: SSEEvent }
  | { type: "error"; event: SSEEvent }
  | { type: "user_message"; event: SSEEvent };

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3 } },
  exit: { opacity: 0, y: -8, transition: { duration: 0.2 } },
};

function buildTimelineItems(events: SSEEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  // Map from tool name to the index in items array for pending (unresolved) tool_calls
  const pendingTools = new Map<string, number>();

  for (const event of events) {
    switch (event.event_type) {
      case "thinking":
        items.push({ type: "thinking", event });
        break;
      case "tool_call": {
        const name = event.data.name as string;
        const idx = items.length;
        items.push({ type: "paired_tool", toolCall: event });
        pendingTools.set(name, idx);
        break;
      }
      case "tool_result": {
        const name = event.data.name as string;
        const pendingIdx = pendingTools.get(name);
        if (pendingIdx !== undefined) {
          const item = items[pendingIdx] as { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent };
          item.toolResult = event;
          pendingTools.delete(name);
        }
        // If no pending match, ignore (shouldn't happen with ordered events)
        break;
      }
      case "approval_required":
        items.push({ type: "approval_required", event });
        break;
      case "ask_human":
        items.push({ type: "ask_human", event });
        break;
      case "error":
        items.push({ type: "error", event });
        break;
      case "user_message":
        items.push({ type: "user_message", event });
        break;
      default:
        break;
    }
  }
  return items;
}

export function EventTimeline({ incidentId, savedToMemory, summaryMarkdown }: EventTimelineProps) {
  const {
    events,
    discoveryAgentState,
    historyAgentState,
    kbAgentState,
    phaseState,
    thinkingContent,
  } = useIncidentStreamStore();

  // Connections for resolving connection_id → name
  const { data: connections } = useQuery({
    queryKey: ["connections"],
    queryFn: getConnections,
    staleTime: 5 * 60 * 1000,
  });

  const connectionMap = useMemo(() => {
    const map = new Map<string, string>();
    if (connections) {
      for (const c of connections) {
        map.set(c.id, c.name);
      }
    }
    return map;
  }, [connections]);

  const hasDiscovery =
    discoveryAgentState.events.length > 0 ||
    !!discoveryAgentState.thinkingContent;
  const hasHistory =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent;
  const hasKB =
    kbAgentState.events.length > 0 || !!kbAgentState.thinkingContent;
  const hasGatherContext = hasDiscovery || hasHistory || hasKB;

  const mainEvents = events.filter((e) => e.event_type !== "summary");
  const summaryEvent = events.find((e) => e.event_type === "summary");
  const hasInvestigation = mainEvents.length > 0 || !!thinkingContent;
  const hasReport = !!summaryEvent || !!summaryMarkdown;

  // Build paired timeline items
  const timelineItems = useMemo(() => buildTimelineItems(mainEvents), [mainEvents]);

  // Compute base timestamp and stats for investigation phase
  const { baseTimestamp, phaseSubtitle } = useMemo(() => {
    if (mainEvents.length === 0) return { baseTimestamp: "", phaseSubtitle: "" };

    const base = mainEvents[0].timestamp;
    const last = mainEvents[mainEvents.length - 1].timestamp;
    const dur = formatDuration(base, last);
    const toolCount = mainEvents.filter((e) => e.event_type === "tool_call").length;

    const parts: string[] = [];
    if (dur && dur !== "0s") parts.push(dur);
    if (toolCount > 0) parts.push(`${toolCount} 次工具调用`);
    return { baseTimestamp: base, phaseSubtitle: parts.join(" · ") };
  }, [mainEvents]);

  // Context gathering subtitle
  const contextSubtitle = useMemo(() => {
    const allContextEvents = [
      ...discoveryAgentState.events,
      ...historyAgentState.events,
      ...kbAgentState.events,
    ];
    if (allContextEvents.length < 2) return "";
    const sorted = allContextEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const dur = formatDuration(sorted[0].timestamp, sorted[sorted.length - 1].timestamp);
    return dur !== "0s" ? dur : "";
  }, [discoveryAgentState.events, historyAgentState.events, kbAgentState.events]);

  return (
    <div className="space-y-3 p-4" data-testid="event-timeline">
      {/* Phase 1: Context Gathering */}
      {(hasGatherContext || phaseState.contextGathering !== "pending") && (
        <PhaseSection
          title="上下文收集"
          subtitle={contextSubtitle}
          status={phaseState.contextGathering}
          icon={Search}
        >
          <div className="space-y-3">
            {hasDiscovery && (
              <SubAgentCard
                agentName="discovery"
                events={discoveryAgentState.events}
                isStreaming={!!discoveryAgentState.thinkingContent}
                streamingContent={discoveryAgentState.thinkingContent}
              />
            )}
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
        </PhaseSection>
      )}

      {/* Phase 2: Investigation */}
      {(hasInvestigation || phaseState.investigation !== "pending") && (
        <PhaseSection
          title="调查分析"
          subtitle={phaseSubtitle}
          status={phaseState.investigation}
          icon={Brain}
        >
          <div className="space-y-3">
            <AnimatePresence initial={false}>
              {timelineItems.map((item, i) => {
                switch (item.type) {
                  case "thinking":
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <ThinkingBubble content={item.event.data.content as string} />
                      </motion.div>
                    );
                  case "paired_tool": {
                    const connId = item.toolCall.data.args
                      ? (item.toolCall.data.args as Record<string, unknown>).connection_id as string | undefined
                      : undefined;
                    const connName = connId ? connectionMap.get(connId) : undefined;
                    const relTime = baseTimestamp
                      ? formatRelativeTime(item.toolCall.timestamp, baseTimestamp)
                      : undefined;
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <ToolCallCard
                          name={item.toolCall.data.name as string}
                          args={item.toolCall.data.args as Record<string, unknown>}
                          output={item.toolResult?.data.output as string | undefined}
                          isExecuting={!item.toolResult}
                          relativeTime={relTime}
                          connectionInfo={connName}
                        />
                      </motion.div>
                    );
                  }
                  case "approval_required":
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <ApprovalCard
                          toolCall={item.event.data.tool_args as Record<string, unknown>}
                          approvalId={item.event.data.approval_id as string}
                        />
                      </motion.div>
                    );
                  case "ask_human":
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
                          <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                          <div>
                            <p className="text-sm font-medium text-amber-800">
                              Agent 需要更多信息
                            </p>
                            <p className="mt-1 text-sm text-amber-700">
                              {item.event.data.question as string}
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    );
                  case "user_message": {
                    const relTime = baseTimestamp
                      ? formatRelativeTime(item.event.timestamp, baseTimestamp)
                      : undefined;
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <UserMessageBubble
                          content={item.event.data.content as string}
                          relativeTime={relTime}
                        />
                      </motion.div>
                    );
                  }
                  case "error":
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
                          Error: {item.event.data.message as string}
                        </div>
                      </motion.div>
                    );
                  default:
                    return null;
                }
              })}
            </AnimatePresence>

            {/* Live thinking stream */}
            <AnimatePresence>
              {thinkingContent && (
                <motion.div
                  key="live-thinking"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                >
                  <ThinkingBubble content={thinkingContent} isStreaming />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </PhaseSection>
      )}

      {/* Phase 3: Report */}
      {hasReport && (
        <PhaseSection
          title="调查报告"
          status={phaseState.report}
          icon={FileText}
          defaultExpanded={phaseState.report === "completed"}
        >
          <SummarySection
            markdown={summaryEvent ? (summaryEvent.data.summary_md as string) : summaryMarkdown!}
            incidentId={incidentId}
            savedToMemory={savedToMemory}
          />
        </PhaseSection>
      )}
    </div>
  );
}
