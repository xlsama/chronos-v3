import { useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Search, Brain, FileText, MessageCircleQuestion, Loader2, Square, Sparkles } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { getServers } from "@/api/servers";
import { formatRelativeTime, formatDuration } from "@/lib/utils";
import type { SSEEvent } from "@/lib/types";
import { Markdown } from "@/components/ui/markdown";
import { PhaseSection } from "./phase-section";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { ApprovalCard } from "./approval-card";
import { SummarySection } from "./summary-section";
import { SubAgentCard } from "./sub-agent-card";
import { UserMessageBubble } from "./user-message-bubble";
import { AnswerCard } from "./answer-card";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

interface EventTimelineProps {
  summaryMarkdown?: string | null;
}

type TimelineItem =
  | { type: "thinking"; event: SSEEvent }
  | { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent }
  | { type: "approval_required"; event: SSEEvent }
  | { type: "ask_human"; event: SSEEvent }
  | { type: "error"; event: SSEEvent }
  | { type: "user_message"; event: SSEEvent }
  | { type: "incident_stopped"; event: SSEEvent }
  | { type: "skill_used"; event: SSEEvent }
  | { type: "answer"; event: SSEEvent };

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
      case "incident_stopped":
        items.push({ type: "incident_stopped", event });
        break;
      case "skill_used":
        items.push({ type: "skill_used", event });
        break;
      case "answer":
        items.push({ type: "answer", event });
        break;
      case "thinking_done":
      case "agent_status":
        break;  // Don't render
      default:
        break;
    }
  }
  return items;
}

function LiveThinkingSection() {
  const thinkingContent = useIncidentStreamStore((s) => s.thinkingContent);
  return (
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
  );
}

function ReportStreamSection() {
  const reportStreamContent = useIncidentStreamStore((s) => s.reportStreamContent);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        正在生成排查报告...
      </div>
      {reportStreamContent && (
        <div className="rounded-lg border-l-2 border-primary bg-muted p-4 text-sm">
          <Markdown content={reportStreamContent} streaming variant="compact" />
        </div>
      )}
    </div>
  );
}

export function EventTimeline({ summaryMarkdown }: EventTimelineProps) {
  const events = useIncidentStreamStore((s) => s.events);
  const historyAgentState = useIncidentStreamStore((s) => s.historyAgentState);
  const kbAgentState = useIncidentStreamStore((s) => s.kbAgentState);
  const phaseState = useIncidentStreamStore((s) => s.phaseState);
  const hasThinking = useIncidentStreamStore((s) => !!s.thinkingContent);

  // Servers for resolving server_id → name
  const { data: serversData } = useQuery({
    queryKey: ["servers", "all"],
    queryFn: () => getServers({ page_size: 200 }),
    staleTime: 5 * 60 * 1000,
  });

  const serverMap = useMemo(() => {
    const map = new Map<string, string>();
    if (serversData?.items) {
      for (const s of serversData.items) {
        map.set(s.id, s.name);
      }
    }
    return map;
  }, [serversData]);

  const hasHistory =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent ||
    historyAgentState.status !== "idle";
  const hasKB =
    kbAgentState.events.length > 0 ||
    !!kbAgentState.thinkingContent ||
    kbAgentState.status !== "idle";
  const hasGatherContext = hasHistory || hasKB;

  const mainEvents = events.filter((e) => e.event_type !== "summary");
  const summaryEvent = events.find((e) => e.event_type === "summary");
  const hasInvestigation = mainEvents.length > 0 || hasThinking;
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
      ...historyAgentState.events,
      ...kbAgentState.events,
    ];
    if (allContextEvents.length < 2) return "";
    const sorted = allContextEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const dur = formatDuration(sorted[0].timestamp, sorted[sorted.length - 1].timestamp);
    return dur !== "0s" ? dur : "";
  }, [historyAgentState.events, kbAgentState.events]);

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
            {hasHistory && (
              <SubAgentCard
                agentName="history"
                events={historyAgentState.events}
                status={historyAgentState.status}
                streamingContent={historyAgentState.thinkingContent}
                forceExpanded={phaseState.contextGathering === "active"}
              />
            )}
            {hasKB && (
              <SubAgentCard
                agentName="kb"
                events={kbAgentState.events}
                status={kbAgentState.status}
                streamingContent={kbAgentState.thinkingContent}
                forceExpanded={phaseState.contextGathering === "active"}
              />
            )}
          </div>
        </PhaseSection>
      )}

      {/* Phase 2: Investigation */}
      {(hasInvestigation || phaseState.investigation !== "pending") && (
        <PhaseSection
          title="排查处置"
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
                    const serverId = item.toolCall.data.args
                      ? (item.toolCall.data.args as Record<string, unknown>).server_id as string | undefined
                      : undefined;
                    const serverName = serverId ? serverMap.get(serverId) : undefined;
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
                          serverInfo={serverName}
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
                  case "incident_stopped":
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4">
                          <Square className="h-5 w-5 shrink-0 text-gray-500" />
                          <p className="text-sm text-gray-600">事件已被手动停止</p>
                        </div>
                      </motion.div>
                    );
                  case "skill_used": {
                    const skillName = item.event.data.skill_name as string;
                    const skillContent = item.event.data.content as string;
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <div className="flex items-center gap-2 text-sm text-indigo-700">
                          <Sparkles className="h-4 w-4" />
                          <span>使用技能：</span>
                          <HoverCard>
                            <HoverCardTrigger className="cursor-pointer underline decoration-dotted">
                              {skillName}
                            </HoverCardTrigger>
                            <HoverCardContent className="w-96 max-h-80 overflow-y-auto">
                              <Markdown content={skillContent} variant="compact" />
                            </HoverCardContent>
                          </HoverCard>
                        </div>
                      </motion.div>
                    );
                  }
                  case "answer":
                    return (
                      <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                        <AnswerCard content={item.event.data.content as string} />
                      </motion.div>
                    );
                  default:
                    return null;
                }
              })}
            </AnimatePresence>

            {/* Live thinking stream — isolated component to avoid re-rendering timeline */}
            <LiveThinkingSection />
          </div>
        </PhaseSection>
      )}

      {/* Phase 3: Report */}
      {(hasReport || phaseState.report !== "pending") && (
        <PhaseSection
          title="归档总结"
          status={phaseState.report}
          icon={FileText}
          defaultExpanded={phaseState.report !== "pending"}
        >
          {phaseState.report === "active" && <ReportStreamSection />}
          {phaseState.report === "completed" && (
            <SummarySection
              markdown={summaryEvent ? (summaryEvent.data.summary_md as string) : summaryMarkdown!}
            />
          )}
        </PhaseSection>
      )}
    </div>
  );
}
