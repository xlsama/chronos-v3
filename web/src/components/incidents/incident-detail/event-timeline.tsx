import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Search, Brain, MessageCircleQuestion, Loader2, Square, Sparkles, CheckCircle, ChevronRight } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { confirmResolution } from "@/api/incidents";
import { Button } from "@/components/ui/button";
import { getServers } from "@/api/servers";
import { getServices } from "@/api/services";
import { cn, formatRelativeTime, formatDuration } from "@/lib/utils";
import { timelineItemVariants } from "@/lib/motion";
import type { SSEEvent } from "@/lib/types";
import { Markdown } from "@/components/ui/markdown";
import { PhaseSection } from "./phase-section";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { ApprovalCard } from "./approval-card";

import { SubAgentCard } from "./sub-agent-card";
import { UserMessageBubble } from "./user-message-bubble";
import { AnswerCard } from "./answer-card";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";

interface EventTimelineProps {
  incidentId: string;
}

type TimelineItem =
  | { type: "thinking"; event: SSEEvent }
  | { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent }
  | { type: "approval_required"; event: SSEEvent }
  | { type: "ask_human"; event: SSEEvent }
  | { type: "error"; event: SSEEvent }
  | { type: "user_message"; event: SSEEvent }
  | { type: "incident_stopped"; event: SSEEvent }
  | { type: "skill_read"; event: SSEEvent }
  | { type: "answer"; event: SSEEvent };


function buildTimelineItems(events: SSEEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  // Map from tool_call_id to the index in items array for pending (unresolved) tool_calls
  const pendingTools = new Map<string, number>();

  for (const [idx, event] of events.entries()) {
    switch (event.event_type) {
      case "thinking":
        items.push({ type: "thinking", event });
        break;
      case "tool_call": {
        const name = event.data.name as string;
        const callId = (event.data.tool_call_id as string) || `${name}_${idx}`;
        const itemIdx = items.length;
        items.push({ type: "paired_tool", toolCall: event });
        pendingTools.set(callId, itemIdx);
        break;
      }
      case "tool_result": {
        const name = event.data.name as string;
        const callId = (event.data.tool_call_id as string) || `${name}_${idx}`;
        const pendingIdx = pendingTools.get(callId);
        if (pendingIdx !== undefined) {
          const item = items[pendingIdx] as { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent };
          item.toolResult = event;
          pendingTools.delete(callId);
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
      case "skill_read":
        if (event.data.success !== false) {
          items.push({ type: "skill_read", event });
        }
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

function formatErrorMessage(message: string): string {
  const trimmed = message.trim();
  if (!trimmed) {
    return "排查流程执行失败，请查看后端日志并补充更多事件信息后重试。";
  }

  const normalized = trimmed.replace(/^['"]+|['"]+$/g, "");
  if (normalized === "find") {
    return "Agent 调用了未注册的工具 `find`。当前信息不足，无法直接开始排查，请补充具体故障现象、受影响服务和发生时间后重试。";
  }

  if (/^[a-z_]+$/i.test(normalized)) {
    return `Agent 调用了未注册的工具 \`${normalized}\`。当前信息不足，请补充具体故障现象、受影响服务和发生时间。`;
  }

  return trimmed;
}

function SkillReadCard({ skillName, skillContent }: { skillName: string; skillContent: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="flex items-center gap-2 text-sm text-indigo-700">
        <Sparkles className="h-4 w-4" />
        <span>读取技能：</span>
        <CollapsibleTrigger className="inline-flex items-center gap-1 cursor-pointer underline decoration-dotted hover:text-indigo-900">
          <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
          {skillName}
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent>
        <div className="mt-2 ml-6 rounded-md border border-indigo-100 bg-indigo-50/30 p-3 max-h-80 overflow-y-auto">
          <Markdown content={skillContent} variant="compact" className="card-markdown card-markdown--indigo" />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function LiveThinkingSection() {
  const thinkingContent = useIncidentStreamStore((s) => s.thinkingContent);
  return (
    <AnimatePresence>
      {thinkingContent && (
        <motion.div
          key="live-thinking"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <ThinkingBubble content={thinkingContent} isStreaming />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function LiveAskHumanSection() {
  const askHumanStreamContent = useIncidentStreamStore((s) => s.askHumanStreamContent);
  return (
    <AnimatePresence>
      {askHumanStreamContent && (
        <motion.div
          key="live-ask-human"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
            <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div>
              <p className="text-sm font-medium text-amber-800">
                Agent 需要更多信息
              </p>
              <Markdown
                content={askHumanStreamContent}
                streaming
                variant="compact"
                className="mt-1 card-markdown card-markdown--amber"
              />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function LiveAnswerSection() {
  const answerContent = useIncidentStreamStore((s) => s.answerContent);
  return (
    <AnimatePresence>
      {answerContent && (
        <motion.div
          key="live-answer"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <AnswerCard content={answerContent} isStreaming />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ResolutionConfirmCard({ incidentId }: { incidentId: string }) {
  const resolutionConfirmRequired = useIncidentStreamStore((s) => s.resolutionConfirmRequired);
  const resolutionConfirmResolved = useIncidentStreamStore((s) => s.resolutionConfirmResolved);
  const setResolutionConfirmResolved = useIncidentStreamStore((s) => s.setResolutionConfirmResolved);

  const queryClient = useQueryClient();
  const confirmMutation = useMutation({
    mutationFn: () => confirmResolution(incidentId),
    onMutate: () => {
      setResolutionConfirmResolved(true);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  if (!resolutionConfirmRequired) return null;

  const resolved = resolutionConfirmResolved;

  return (
    <div
      className={cn(
        "rounded-lg border p-4 space-y-3",
        resolved
          ? "border-green-200 bg-green-50/30"
          : "border-blue-200 bg-blue-50/30",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 text-sm font-medium",
          resolved ? "text-green-800" : "text-blue-800",
        )}
      >
        <CheckCircle className="h-5 w-5" />
        {resolved ? "已确认解决" : "问题是否已解决？"}
      </div>
      <p className="text-xs text-muted-foreground">
        {resolved ? "问题已标记为解决" : "如未解决，请在下方输入栏继续提问"}
      </p>
      {!resolved && (
        <Button
          size="sm"
          onClick={() => confirmMutation.mutate()}
          disabled={confirmMutation.isPending}
        >
          已解决
        </Button>
      )}
    </div>
  );
}

export function EventTimeline({ incidentId }: EventTimelineProps) {
  const events = useIncidentStreamStore((s) => s.events);
  const historyAgentState = useIncidentStreamStore((s) => s.historyAgentState);
  const kbAgentState = useIncidentStreamStore((s) => s.kbAgentState);
  const phaseState = useIncidentStreamStore((s) => s.phaseState);
  const hasThinking = useIncidentStreamStore((s) => !!s.thinkingContent);
  const hasAnswerStream = useIncidentStreamStore((s) => !!s.answerContent);
  const hasAskHumanStream = useIncidentStreamStore((s) => !!s.askHumanStreamContent);

  // Servers for resolving server_id → name
  const { data: serversData } = useQuery({
    queryKey: ["servers", "all"],
    queryFn: () => getServers({ page_size: 200 }),
    staleTime: 5 * 60 * 1000,
  });

  // Services for resolving service_id → name
  const { data: servicesData } = useQuery({
    queryKey: ["services", "all"],
    queryFn: () => getServices({ page_size: 200 }),
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

  const serviceMap = useMemo(() => {
    const map = new Map<string, string>();
    if (servicesData?.items) {
      for (const s of servicesData.items) {
        map.set(s.id, s.name);
      }
    }
    return map;
  }, [servicesData]);

  const contextActive = phaseState.contextGathering === "active";

  const hasHistory = contextActive ||
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent ||
    historyAgentState.status !== "idle";
  const hasKB = contextActive ||
    kbAgentState.events.length > 0 ||
    !!kbAgentState.thinkingContent ||
    kbAgentState.status !== "idle";
  const hasGatherContext = hasHistory || hasKB;
  const hasBothContextCards = hasHistory && hasKB;

  const hasSubAgentContent =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent ||
    kbAgentState.events.length > 0 ||
    !!kbAgentState.thinkingContent;

  const shouldUseFixedContextLayout =
    contextActive && hasGatherContext && hasSubAgentContent;

  const mainEvents = events.filter((e) => e.event_type !== "done");
  const hasInvestigation = mainEvents.length > 0 || hasThinking || hasAnswerStream || hasAskHumanStream;

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
          contentClassName={cn(
            shouldUseFixedContextLayout &&
              // Fixed panel height keeps the sub-agent area stable within the detail view
              // while accounting for the page header, timeline padding and input bar.
              "h-[calc(100dvh-20rem)] min-h-[18rem] overflow-hidden md:h-[calc(100dvh-18rem)]",
          )}
        >
          <div
            className={cn(
              "min-h-0",
              shouldUseFixedContextLayout
                ? hasBothContextCards
                  ? "grid h-full grid-rows-2 gap-3"
                  : "flex h-full flex-col"
                : "space-y-3",
            )}
            data-testid="context-subagent-layout"
          >
            {hasHistory && (
              <SubAgentCard
                className={cn(
                  shouldUseFixedContextLayout && "h-full min-h-0 overflow-hidden",
                )}
                agentName="history"
                events={historyAgentState.events}
                status={historyAgentState.status}
                streamingContent={historyAgentState.thinkingContent}
                forceExpanded={phaseState.contextGathering === "active"}
              />
            )}
            {hasKB && (
              <SubAgentCard
                className={cn(
                  shouldUseFixedContextLayout && "h-full min-h-0 overflow-hidden",
                )}
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
          defaultExpanded
        >
          <div className="space-y-3">
            <AnimatePresence initial={false}>
              {timelineItems.map((item, i) => {
                switch (item.type) {
                  case "thinking":
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <ThinkingBubble content={item.event.data.content as string} />
                      </motion.div>
                    );
                  case "paired_tool": {
                    const toolName = item.toolCall.data.name as string;
                    const toolArgs = item.toolCall.data.args as Record<string, unknown> | undefined;

                    // Resolve server/service info based on tool type
                    let serverInfo: string | undefined;
                    let serviceInfo: string | undefined;
                    if (toolName === "ssh_bash") {
                      const serverId = toolArgs?.server_id as string | undefined;
                      serverInfo = serverId ? serverMap.get(serverId) : undefined;
                    } else if (toolName === "service_exec") {
                      const serviceId = toolArgs?.service_id as string | undefined;
                      serviceInfo = serviceId ? serviceMap.get(serviceId) : undefined;
                    }

                    const relTime = baseTimestamp
                      ? formatRelativeTime(item.toolCall.timestamp, baseTimestamp)
                      : undefined;
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <ToolCallCard
                          name={toolName}
                          args={toolArgs}
                          output={item.toolResult?.data.output as string | undefined}
                          isExecuting={!item.toolResult}
                          relativeTime={relTime}
                          serverInfo={serverInfo}
                          serviceInfo={serviceInfo}
                        />
                      </motion.div>
                    );
                  }
                  case "approval_required":
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <ApprovalCard
                          toolCall={item.event.data.tool_args as Record<string, unknown>}
                          approvalId={item.event.data.approval_id as string}
                        />
                      </motion.div>
                    );
                  case "ask_human":
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
                          <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                          <div>
                            <p className="text-sm font-medium text-amber-800">
                              Agent 需要更多信息
                            </p>
                            <Markdown
                              content={item.event.data.question as string}
                              variant="compact"
                              className="mt-1 card-markdown card-markdown--amber"
                            />
                          </div>
                        </div>
                      </motion.div>
                    );
                  case "user_message":
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <UserMessageBubble
                          content={item.event.data.content as string}
                          attachments={item.event.data.attachments as { filename: string; content_type: string; size: number; preview_url: string | null }[]}
                          attachment_ids={item.event.data.attachment_ids as string[]}
                          attachments_meta={item.event.data.attachments_meta as { id: string; filename: string; content_type: string; size: number }[]}
                        />
                      </motion.div>
                    );

                  case "error":
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <div className="rounded-md border border-destructive bg-destructive/10 p-3">
                          <Markdown
                            content={formatErrorMessage(item.event.data.message as string)}
                            variant="compact"
                            className="card-markdown card-markdown--destructive"
                          />
                        </div>
                      </motion.div>
                    );
                  case "incident_stopped":
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4">
                          <Square className="h-5 w-5 shrink-0 text-gray-500" />
                          <p className="text-sm text-gray-600">事件已被手动停止</p>
                        </div>
                      </motion.div>
                    );
                  case "skill_read": {
                    const skillName = (item.event.data.skill_name as string) || (item.event.data.skill_slug as string);
                    const skillContent = item.event.data.content as string;
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
                        <SkillReadCard skillName={skillName} skillContent={skillContent} />
                      </motion.div>
                    );
                  }
                  case "answer":
                    return (
                      <motion.div key={i} variants={timelineItemVariants} initial="hidden" animate="visible">
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

            {/* Live ask_human stream — shows question as it streams in */}
            <LiveAskHumanSection />

            {/* Live answer stream — shows answer as it streams in */}
            <LiveAnswerSection />

            {/* Resolution confirm card */}
            <ResolutionConfirmCard incidentId={incidentId} />
          </div>
        </PhaseSection>
      )}

      {/* Empty state: nothing rendered yet */}
      {!hasGatherContext &&
        phaseState.contextGathering === "pending" &&
        !hasInvestigation &&
        phaseState.investigation === "pending" && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mb-3" />
          <p className="text-sm">正在连接，等待 Agent 开始处理...</p>
        </div>
      )}
    </div>
  );
}
