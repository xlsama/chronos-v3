import { useMemo, useState } from "react";
import { MessageCircleQuestion, Sparkles, CheckCircle } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { confirmResolution } from "@/api/incidents";
import { Button } from "@/components/ui/button";
import { getServers } from "@/api/servers";
import { getServices } from "@/api/services";
import { SkillViewer } from "@/components/skills/skill-viewer";
import { cn, formatRelativeTime, formatDuration } from "@/lib/utils";
import type { SSEEvent } from "@/lib/types";
import { Markdown } from "@/components/ui/markdown";
import { PhaseSection } from "./phase-section";
import { TextDotsLoader } from "@/components/ui/loader";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";

import { SubAgentCard } from "./sub-agent-card";
import { TimelineDivider } from "./timeline-divider";
import { UserMessageBubble } from "./user-message-bubble";
import { AnswerCard } from "./answer-card";
import { PlannerContent } from "./planner-phase-section";
import { EvaluationInlineCard, LiveEvaluatorThinkingSection } from "./evaluator-phase-section";
import type { EvaluationResult } from "@/stores/incident-stream";

interface EventTimelineProps {
  incidentId: string;
  incidentStatus?: string;
}

type TimelineItem =
  | { type: "thinking"; event: SSEEvent }
  | { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent }
  | { type: "approval_tool"; approvalEvent: SSEEvent; toolCall?: SSEEvent; toolResult?: SSEEvent }
  | { type: "ask_human"; event: SSEEvent }
  | { type: "error"; event: SSEEvent }
  | { type: "user_message"; event: SSEEvent }
  | { type: "incident_stopped"; event: SSEEvent }
  | { type: "skill_read"; event: SSEEvent }
  | { type: "answer"; event: SSEEvent }
  | { type: "agent_interrupted"; event: SSEEvent }
  | { type: "evaluation"; event: SSEEvent }
  | { type: "done"; event: SSEEvent };

function buildTimelineItems(events: SSEEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  // Map from tool_call_id (run_id) to the index in items array for pending tool_calls
  const pendingTools = new Map<string, number>();
  // Map from approval_id to the index in items array for approval_tool items
  const pendingApprovals = new Map<string, number>();

  for (const [idx, event] of events.entries()) {
    switch (event.event_type) {
      case "thinking":
        items.push({ type: "thinking", event });
        break;
      case "tool_use": {
        const name = event.data.name as string;
        const callId = (event.data.tool_call_id as string) || `${name}_${idx}`;
        const approvalId = event.data.approval_id as string | undefined;

        // Check if this tool_use carries an approval_id linking to a pending approval
        const approvalIdx = approvalId ? pendingApprovals.get(approvalId) : undefined;
        if (approvalIdx !== undefined) {
          // Merge into the existing approval_tool item
          const item = items[approvalIdx] as {
            type: "approval_tool";
            approvalEvent: SSEEvent;
            toolCall?: SSEEvent;
            toolResult?: SSEEvent;
          };
          item.toolCall = event;
          // Also track in pendingTools so tool_result can find it via run_id
          pendingTools.set(callId, approvalIdx);
          pendingApprovals.delete(approvalId!);
        } else {
          const itemIdx = items.length;
          items.push({ type: "paired_tool", toolCall: event });
          pendingTools.set(callId, itemIdx);
        }
        break;
      }
      case "tool_result": {
        const name = event.data.name as string;
        const callId = (event.data.tool_call_id as string) || `${name}_${idx}`;
        const pendingIdx = pendingTools.get(callId);
        if (pendingIdx !== undefined) {
          (items[pendingIdx] as { toolResult?: SSEEvent }).toolResult = event;
          pendingTools.delete(callId);
        }
        break;
      }
      case "approval_required": {
        const approvalId = event.data.approval_id as string;
        const itemIdx = items.length;
        items.push({ type: "approval_tool", approvalEvent: event });
        if (approvalId) {
          pendingApprovals.set(approvalId, itemIdx);
        }
        break;
      }
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
      case "agent_interrupted":
        items.push({ type: "agent_interrupted", event });
        break;
      case "done":
        items.push({ type: "done", event });
        break;
      case "skill_read":
        if (event.data.success !== false) {
          items.push({ type: "skill_read", event });
        }
        break;
      case "answer":
        items.push({ type: "answer", event });
        break;
      case "evaluation_started": {
        // Push loading card; will be replaced in-place by evaluation_completed
        items.push({ type: "evaluation", event });
        break;
      }
      case "evaluation_completed": {
        // Replace pending evaluation_started item if exists
        const pendingIdx = items.findLastIndex((it) => it.type === "evaluation" && !it.event.data.result);
        if (pendingIdx !== -1) {
          items[pendingIdx] = { type: "evaluation", event };
        } else {
          items.push({ type: "evaluation", event });
        }
        break;
      }
      case "thinking_done":
      case "agent_status":
        break; // Don't render
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

function SkillReadCard({ skillName, skillSlug }: { skillName: string; skillSlug: string }) {
  const [viewingSlug, setViewingSlug] = useState<string | null>(null);

  return (
    <>
      <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5 text-blue-400" />
        <span>读取技能：</span>
        <button
          className="cursor-pointer font-medium text-blue-700 underline decoration-dotted underline-offset-2 hover:text-blue-900"
          onClick={() => setViewingSlug(skillSlug)}
        >
          {skillName}
        </button>
      </div>
      <SkillViewer skillSlug={viewingSlug} onClose={() => setViewingSlug(null)} readOnly />
    </>
  );
}

function WaitingIndicator() {
  const isWaiting = useIncidentStreamStore((s) => s.isWaitingForAgent);
  if (!isWaiting) return null;
  return (
    <div className="animate-in fade-in duration-150 px-1 py-2">
      <TextDotsLoader text="Agent 思考中" size="sm" />
    </div>
  );
}

function LiveThinkingSection() {
  const thinkingContent = useIncidentStreamStore((s) => s.thinkingContent);
  if (!thinkingContent) return null;
  return (
    <div className="animate-in fade-in duration-150">
      <ThinkingBubble content={thinkingContent} isStreaming />
    </div>
  );
}

function LiveAskHumanSection() {
  const askHumanStreamContent = useIncidentStreamStore((s) => s.askHumanStreamContent);
  if (!askHumanStreamContent) return null;
  return (
    <div className="animate-in fade-in duration-150">
      <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
        <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div>
          <p className="text-sm font-medium text-amber-800">Agent 需要更多信息</p>
          <Markdown
            content={askHumanStreamContent}
            streaming
            variant="compact"
            className="mt-1 card-markdown card-markdown--amber"
          />
        </div>
      </div>
    </div>
  );
}

function LiveAnswerSection() {
  const answerContent = useIncidentStreamStore((s) => s.answerContent);
  if (!answerContent) return null;
  return (
    <div className="animate-in fade-in duration-150">
      <AnswerCard content={answerContent} isStreaming />
    </div>
  );
}

function ResolutionConfirmCard({
  incidentId,
  incidentStatus,
}: {
  incidentId: string;
  incidentStatus?: string;
}) {
  const resolutionConfirmRequired = useIncidentStreamStore((s) => s.resolutionConfirmRequired);
  const resolutionConfirmResolved = useIncidentStreamStore((s) => s.resolutionConfirmResolved);
  const setResolutionConfirmResolved = useIncidentStreamStore(
    (s) => s.setResolutionConfirmResolved,
  );

  const TERMINAL = ["resolved", "stopped"];
  const isTerminal = !!incidentStatus && TERMINAL.includes(incidentStatus);

  const queryClient = useQueryClient();
  const confirmMutation = useMutation({
    mutationFn: () => confirmResolution(incidentId),
    onMutate: () => {
      setResolutionConfirmResolved(true);
    },
    onError: () => {
      setResolutionConfirmResolved(false);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  if (!resolutionConfirmRequired) return null;

  const resolved = resolutionConfirmResolved || isTerminal;

  return (
    <div
      className={cn(
        "rounded-lg border p-4 space-y-3",
        resolved ? "border-green-200 bg-green-50/30" : "border-blue-200 bg-blue-50/30",
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

export function EventTimeline({ incidentId, incidentStatus }: EventTimelineProps) {
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

  const isActiveIncident =
    incidentStatus === "open" ||
    incidentStatus === "investigating" ||
    incidentStatus === "interrupted";
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

  const plannerPlanMd = useIncidentStreamStore((s) => s.plannerPlanMd);

  const hasSubAgentContent =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent ||
    kbAgentState.events.length > 0 ||
    !!kbAgentState.thinkingContent;

  const shouldUseFixedContextLayout = contextActive && hasGatherContext && hasSubAgentContent;

  const mainEvents = events;
  const hasInvestigation =
    mainEvents.length > 0 || hasThinking || hasAnswerStream || hasAskHumanStream;

  // Transitional state: both sub-agents done but investigation phase hasn't started yet
  // (2-5s gap while main LLM processes context before emitting first token)
  const bothSubAgentsDone =
    (historyAgentState.status === "completed" ||
      historyAgentState.status === "failed" ||
      historyAgentState.status === "idle") &&
    (kbAgentState.status === "completed" ||
      kbAgentState.status === "failed" ||
      kbAgentState.status === "idle") &&
    (historyAgentState.status !== "idle" || kbAgentState.status !== "idle");
  const isTransitioningToInvestigation =
    isActiveIncident &&
    phaseState.contextGathering === "active" &&
    phaseState.investigation === "pending" &&
    bothSubAgentsDone;

  // Phase visibility
  const showContextGathering =
    hasGatherContext || phaseState.contextGathering !== "pending" || isActiveIncident;
  const showPlanning = !!plannerPlanMd || phaseState.planning !== "pending";
  const showInvestigation =
    hasInvestigation || phaseState.investigation !== "pending" || isTransitioningToInvestigation;

  // Build paired timeline items
  const timelineItems = useMemo(() => buildTimelineItems(mainEvents), [mainEvents]);

  // Compute base timestamp and stats for investigation phase
  const { baseTimestamp, phaseSubtitle } = useMemo(() => {
    if (mainEvents.length === 0) return { baseTimestamp: "", phaseSubtitle: "" };

    const base = mainEvents[0].timestamp;
    const last = mainEvents[mainEvents.length - 1].timestamp;
    const dur = formatDuration(base, last);
    const toolCount = mainEvents.filter((e) => e.event_type === "tool_use").length;

    const parts: string[] = [];
    if (dur && dur !== "0s") parts.push(dur);
    if (toolCount > 0) parts.push(`${toolCount} 次工具调用`);
    return { baseTimestamp: base, phaseSubtitle: parts.join(" · ") };
  }, [mainEvents]);

  // Context gathering subtitle
  const contextSubtitle = useMemo(() => {
    const allContextEvents = [...historyAgentState.events, ...kbAgentState.events];
    if (allContextEvents.length < 2) return "";
    const sorted = allContextEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const dur = formatDuration(sorted[0].timestamp, sorted[sorted.length - 1].timestamp);
    return dur !== "0s" ? dur : "";
  }, [historyAgentState.events, kbAgentState.events]);

  return (
    <div className="px-8 py-4" data-testid="event-timeline">
      {/* Phase 1: Context Gathering */}
      {showContextGathering && (
        <PhaseSection
          title="上下文收集"
          subtitle={contextSubtitle}
          status={phaseState.contextGathering}
          defaultExpanded={phaseState.investigation === "pending" || undefined}
          isLast={!showPlanning && !showInvestigation}
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
      )}

      {/* Phase 2: Planning */}
      {showPlanning && (
        <PhaseSection
          title="制定计划"
          status={phaseState.planning}
          isLast={!showInvestigation}
        >
          <PlannerContent />
        </PhaseSection>
      )}

      {/* Phase 3: Investigation */}
      {showInvestigation && (
        <PhaseSection
          title="排查处置"
          subtitle={phaseSubtitle}
          status={isTransitioningToInvestigation ? "active" : phaseState.investigation}
          defaultExpanded
          isLast
        >
          <div className="space-y-3">
            {timelineItems.map((item, i) => {
              switch (item.type) {
                case "thinking":
                  return (
                    <div key={i}>
                      <ThinkingBubble content={item.event.data.content as string} />
                    </div>
                  );
                case "paired_tool": {
                  const toolName = item.toolCall.data.name as string;
                  const toolArgs = item.toolCall.data.args as Record<string, unknown> | undefined;

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
                    <div key={i}>
                      <ToolCallCard
                        name={toolName}
                        args={toolArgs}
                        output={item.toolResult?.data.output as string | undefined}
                        isExecuting={!item.toolResult}
                        relativeTime={relTime}
                        serverInfo={serverInfo}
                        serviceInfo={serviceInfo}
                      />
                    </div>
                  );
                }
                case "approval_tool": {
                  const approvalData = item.approvalEvent.data;
                  const approvalToolName = (approvalData.tool_name as string) || "";
                  const approvalArgs = approvalData.tool_args as
                    | Record<string, unknown>
                    | undefined;

                  let approvalServerInfo: string | undefined;
                  let approvalServiceInfo: string | undefined;
                  if (approvalToolName === "ssh_bash") {
                    const sid = approvalArgs?.server_id as string | undefined;
                    approvalServerInfo = sid ? serverMap.get(sid) : undefined;
                  } else if (approvalToolName === "service_exec") {
                    const sid = approvalArgs?.service_id as string | undefined;
                    approvalServiceInfo = sid ? serviceMap.get(sid) : undefined;
                  }

                  const approvalRelTime =
                    baseTimestamp && item.toolCall
                      ? formatRelativeTime(item.toolCall.timestamp, baseTimestamp)
                      : undefined;

                  return (
                    <div key={i}>
                      <ToolCallCard
                        name={approvalToolName}
                        args={approvalArgs}
                        output={item.toolResult?.data.output as string | undefined}
                        isExecuting={!!item.toolCall && !item.toolResult}
                        relativeTime={approvalRelTime}
                        serverInfo={approvalServerInfo}
                        serviceInfo={approvalServiceInfo}
                        approvalId={approvalData.approval_id as string}
                        riskLevel={approvalArgs?.risk_level as string | undefined}
                        explanation={approvalArgs?.explanation as string | undefined}
                        incidentStatus={incidentStatus}
                      />
                    </div>
                  );
                }
                case "ask_human":
                  return (
                    <div key={i}>
                      <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
                        <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                        <div>
                          <p className="text-sm font-medium text-amber-800">Agent 需要更多信息</p>
                          <Markdown
                            content={item.event.data.question as string}
                            variant="compact"
                            className="mt-1 card-markdown card-markdown--amber"
                          />
                        </div>
                      </div>
                    </div>
                  );
                case "user_message":
                  return (
                    <div key={i}>
                      <UserMessageBubble
                        content={item.event.data.content as string}
                        attachments={
                          item.event.data.attachments as {
                            filename: string;
                            content_type: string;
                            size: number;
                            preview_url: string | null;
                          }[]
                        }
                        attachment_ids={item.event.data.attachment_ids as string[]}
                        attachments_meta={
                          item.event.data.attachments_meta as {
                            id: string;
                            filename: string;
                            content_type: string;
                            size: number;
                          }[]
                        }
                      />
                    </div>
                  );

                case "error":
                  return (
                    <div key={i}>
                      <div className="rounded-md border border-destructive bg-destructive/10 p-3">
                        <Markdown
                          content={formatErrorMessage(item.event.data.message as string)}
                          variant="compact"
                          className="card-markdown card-markdown--destructive"
                        />
                      </div>
                    </div>
                  );
                case "agent_interrupted":
                  return (
                    <div key={i}>
                      <TimelineDivider type="agent_interrupted" />
                    </div>
                  );
                case "done":
                  return (
                    <div key={i}>
                      <TimelineDivider type="done" />
                    </div>
                  );
                case "incident_stopped":
                  return (
                    <div key={i}>
                      <TimelineDivider type="incident_stopped" />
                    </div>
                  );
                case "skill_read": {
                  const skillName =
                    (item.event.data.skill_name as string) ||
                    (item.event.data.skill_slug as string);
                  const skillSlug = item.event.data.skill_slug as string;
                  return (
                    <div key={i}>
                      <SkillReadCard skillName={skillName} skillSlug={skillSlug} />
                    </div>
                  );
                }
                case "answer":
                  return (
                    <div key={i}>
                      <AnswerCard content={item.event.data.content as string} />
                    </div>
                  );
                case "evaluation": {
                  const evalResult = item.event.data.result as EvaluationResult | undefined;
                  return (
                    <div key={i}>
                      <EvaluationInlineCard result={evalResult} />
                    </div>
                  );
                }
                default:
                  return null;
              }
            })}

            {/* Transitional indicator — waiting for first investigation event after context gathering */}
            {isTransitioningToInvestigation && timelineItems.length === 0 && !hasThinking && (
              <div className="px-1 py-2">
                <TextDotsLoader text="Agent 思考中" size="sm" />
              </div>
            )}

            {/* Waiting indicator — shown between tool_result and next LLM output */}
            <WaitingIndicator />

            {/* Live thinking stream — isolated component to avoid re-rendering timeline */}
            <LiveThinkingSection />

            {/* Live evaluator thinking — shown while evaluator is running */}
            <LiveEvaluatorThinkingSection />

            {/* Live ask_human stream — shows question as it streams in */}
            <LiveAskHumanSection />

            {/* Live answer stream — shows answer as it streams in */}
            <LiveAnswerSection />

            {/* Resolution confirm card */}
            <ResolutionConfirmCard incidentId={incidentId} incidentStatus={incidentStatus} />
          </div>
        </PhaseSection>
      )}
    </div>
  );
}
