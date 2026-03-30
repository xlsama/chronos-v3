import { useCallback, useMemo, useState } from "react";
import { MessageCircleQuestion, CheckCircle, ListTodo, Check, Loader2, ChevronRight } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Virtuoso } from "react-virtuoso";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import type { InvestigationSubAgent } from "@/stores/incident-stream";
import { confirmResolution } from "@/api/incidents";
import { Button } from "@/components/ui/button";
import { getServers } from "@/api/servers";
import { getServices } from "@/api/services";
import { cn, formatRelativeTime, formatDuration } from "@/lib/utils";
import type { SSEEvent } from "@/lib/types";
import { Markdown } from "@/components/ui/markdown";
import { PhaseSection } from "./phase-section";
import { TextDotsLoader } from "@/components/ui/loader";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { SkillReadCard } from "./skill-read-card";

import { SubAgentCard } from "./sub-agent-card";
import { TimelineDivider } from "./timeline-divider";
import { UserMessageBubble } from "./user-message-bubble";
import { AnswerCard } from "./answer-card";
import { PlannerContent } from "./planner-phase-section";

interface EventTimelineProps {
  incidentId: string;
  incidentStatus?: string;
  scrollParent?: HTMLDivElement | null;
}

type TimelineItem =
  | { type: "thinking"; event: SSEEvent; round: number }
  | { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent; round: number }
  | { type: "approval_tool"; approvalEvent: SSEEvent; toolCall?: SSEEvent; toolResult?: SSEEvent; round: number }
  | { type: "plan_update"; event: SSEEvent; round: number }
  | { type: "round_progress"; startEvent: SSEEvent; endEvent?: SSEEvent; round: number }
  | { type: "ask_human"; event: SSEEvent; round: number }
  | { type: "error"; event: SSEEvent; round: number }
  | { type: "user_message"; event: SSEEvent; round: number }
  | { type: "incident_stopped"; event: SSEEvent; round: number }
  | { type: "skill_read"; event: SSEEvent; round: number }
  | { type: "answer"; event: SSEEvent; round: number }
  | { type: "agent_interrupted"; event: SSEEvent; round: number }
  | { type: "done"; event: SSEEvent; round: number };

type MergedItem =
  | { kind: "timeline"; item: TimelineItem; idx: number; ts: string }
  | { kind: "investigation"; inv: InvestigationSubAgent; ts: string };

function buildTimelineItems(events: SSEEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  // Map from tool_call_id (run_id) to the index in items array for pending tool_calls
  const pendingTools = new Map<string, number>();
  // Map from approval_id to the index in items array for approval_tool items
  const pendingApprovals = new Map<string, number>();
  // Track pending round_started for pairing with round_ended
  let pendingRoundIdx: number | undefined;
  // Track the current round number
  let currentRound = 1;

  for (const [idx, event] of events.entries()) {
    switch (event.event_type) {
      case "thinking":
        items.push({ type: "thinking", event, round: currentRound });
        break;
      case "plan_updated":
        items.push({ type: "plan_update", event, round: currentRound });
        break;
      case "round_started":
        pendingRoundIdx = items.length;
        items.push({ type: "round_progress", startEvent: event, round: currentRound });
        break;
      case "round_ended":
        if (pendingRoundIdx !== undefined) {
          (items[pendingRoundIdx] as { endEvent?: SSEEvent }).endEvent = event;
          pendingRoundIdx = undefined;
        }
        // 不再 push 单独的 round_ended item，round_progress 完成态已足够
        currentRound++;
        break;
      case "tool_use": {
        const name = event.data.name as string;
        // Skip the "complete" tool
        if (name === "complete") break;
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
          items.push({ type: "paired_tool", toolCall: event, round: currentRound });
          pendingTools.set(callId, itemIdx);
        }
        break;
      }
      case "tool_result": {
        const name = event.data.name as string;
        // Skip the "complete" tool
        if (name === "complete") break;
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
        items.push({ type: "approval_tool", approvalEvent: event, round: currentRound });
        if (approvalId) {
          pendingApprovals.set(approvalId, itemIdx);
        }
        break;
      }
      case "ask_human":
        items.push({ type: "ask_human", event, round: currentRound });
        break;
      case "error":
        items.push({ type: "error", event, round: currentRound });
        break;
      case "user_message":
        items.push({ type: "user_message", event, round: currentRound });
        break;
      case "incident_stopped":
        items.push({ type: "incident_stopped", event, round: currentRound });
        break;
      case "agent_interrupted":
        items.push({ type: "agent_interrupted", event, round: currentRound });
        break;
      case "done":
        items.push({ type: "done", event, round: currentRound });
        break;
      case "skill_read":
        if (event.data.success !== false) {
          items.push({ type: "skill_read", event, round: currentRound });
        }
        break;
      case "answer":
        items.push({ type: "answer", event, round: currentRound });
        break;
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

  const isTerminal = incidentStatus === "resolved";

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

  // early return 必须放在所有 hooks 之后
  if (incidentStatus === "stopped") return null;
  if (!resolutionConfirmRequired) return null;

  const resolved = resolutionConfirmResolved || isTerminal;

  return (
    <div
      className={cn(
        "rounded-lg border p-4 space-y-3",
        resolved ? "border-green-200 bg-green-50/30 dark:border-green-800 dark:bg-green-950/30" : "border-blue-200 bg-blue-50/30 dark:border-blue-800 dark:bg-blue-950/30",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 text-sm font-medium",
          resolved ? "text-green-800 dark:text-green-200" : "text-blue-800 dark:text-blue-200",
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

export function EventTimeline({ incidentId, incidentStatus, scrollParent }: EventTimelineProps) {
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

  // Investigation sub-agents (new architecture) — declared early for hasInvestigation check
  const investigations = useIncidentStreamStore((s) => s.investigations);
  const activeInvestigationId = useIncidentStreamStore((s) => s.activeInvestigationId);
  const hasInvestigations = investigations.length > 0;

  const hasInvestigation =
    events.length > 0 || hasThinking || hasAnswerStream || hasAskHumanStream || hasInvestigations;

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

  // Transitional state: plan generated but investigation LLM hasn't emitted first token yet
  const isTransitioningFromPlanning =
    isActiveIncident &&
    phaseState.planning === "active" &&
    phaseState.investigation === "pending" &&
    !!plannerPlanMd;

  // Phase visibility
  const showContextGathering =
    hasGatherContext || phaseState.contextGathering !== "pending" || isActiveIncident;
  const showPlanning = !!plannerPlanMd || phaseState.planning !== "pending";
  const showInvestigation =
    hasInvestigation || phaseState.investigation !== "pending" || isTransitioningToInvestigation || isTransitioningFromPlanning;

  // Build paired timeline items
  const timelineItems = useMemo(() => buildTimelineItems(events), [events]);

  // Store round state (legacy)
  const currentRound = useIncidentStreamStore((s) => s.currentRound);
  const roundSummaries = useIncidentStreamStore((s) => s.roundSummaries);

  // Group timeline items by round
  const roundGrouped = useMemo(() => {
    const map = new Map<number, TimelineItem[]>();
    for (const item of timelineItems) {
      const existing = map.get(item.round);
      if (existing) {
        existing.push(item);
      } else {
        map.set(item.round, [item]);
      }
    }
    return map;
  }, [timelineItems]);

  const totalRounds = roundGrouped.size;

  // Track which past rounds are expanded
  const [expandedRounds, setExpandedRounds] = useState<Set<number>>(new Set());
  const toggleRound = useCallback((round: number) => {
    setExpandedRounds((prev) => {
      const next = new Set(prev);
      if (next.has(round)) {
        next.delete(round);
      } else {
        next.add(round);
      }
      return next;
    });
  }, []);

  // Compute base timestamp and stats for investigation phase
  const { baseTimestamp, phaseSubtitle } = useMemo(() => {
    if (events.length === 0) return { baseTimestamp: "", phaseSubtitle: "" };

    const base = events[0].timestamp;
    const last = events[events.length - 1].timestamp;
    const dur = formatDuration(base, last);
    const toolCount = events.filter((e) => e.event_type === "tool_use").length;

    const parts: string[] = [];
    if (dur && dur !== "0s") parts.push(dur);
    if (toolCount > 0) parts.push(`${toolCount} 次工具调用`);
    return { baseTimestamp: base, phaseSubtitle: parts.join(" · ") };
  }, [events]);

  // Context gathering subtitle
  const contextSubtitle = useMemo(() => {
    const allContextEvents = [...historyAgentState.events, ...kbAgentState.events];
    if (allContextEvents.length < 2) return "";
    const sorted = allContextEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const dur = formatDuration(sorted[0].timestamp, sorted[sorted.length - 1].timestamp);
    return dur !== "0s" ? dur : "";
  }, [historyAgentState.events, kbAgentState.events]);

  // Build merged timeline for investigation phase (coordinator events + investigation cards)
  const mergedItems = useMemo((): MergedItem[] => {
    if (!hasInvestigations) return [];

    const merged: MergedItem[] = [];

    for (let i = 0; i < timelineItems.length; i++) {
      const item = timelineItems[i];
      const evt =
        "event" in item ? (item as { event: SSEEvent }).event :
        "toolCall" in item ? (item as { toolCall: SSEEvent }).toolCall :
        "approvalEvent" in item ? (item as { approvalEvent: SSEEvent }).approvalEvent :
        "startEvent" in item ? (item as { startEvent: SSEEvent }).startEvent : null;
      merged.push({ kind: "timeline", item, idx: i, ts: evt?.timestamp || "" });
    }

    for (const inv of investigations) {
      const firstTs = inv.events.length > 0 ? inv.events[0].timestamp : "";
      merged.push({ kind: "investigation", inv, ts: firstTs });
    }

    merged.sort((a, b) => {
      if (!a.ts && !b.ts) return 0;
      if (!a.ts) return 1;
      if (!b.ts) return -1;
      return a.ts.localeCompare(b.ts);
    });

    return merged;
  }, [timelineItems, investigations, hasInvestigations]);

  // Helper: render a single timeline item
  const renderTimelineItem = (item: TimelineItem, i: number) => {
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
              status={item.toolResult?.data.status as "success" | "error" | undefined}
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
              status={item.toolResult?.data.status as "success" | "error" | undefined}
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
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
              <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
              <div>
                <p className="text-sm font-medium text-amber-800 dark:text-amber-200">Agent 需要更多信息</p>
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
      case "plan_update":
        return (
          <div key={i} className="flex items-center gap-1.5 py-1 text-xs text-muted-foreground">
            <ListTodo className="h-3 w-3 text-blue-400" />
            <span>计划已更新</span>
          </div>
        );
      case "round_progress": {
        const isDone = !!item.endEvent;
        const reason = (item.startEvent.data.reason as string) || "hypothesis_transition";
        const loadingText =
          reason === "message_limit"
            ? "消息较多，正在压缩上下文..."
            : "假设状态已变更，正在压缩上下文...";
        const doneText =
          reason === "message_limit"
            ? "上下文已压缩（消息过多）"
            : "上下文已压缩（假设状态变更）";
        return (
          <div key={i} className="flex items-center gap-1.5 py-1 text-xs text-muted-foreground">
            {isDone ? (
              <Check className="h-3 w-3 text-green-500" />
            ) : (
              <Loader2 className="h-3 w-3 animate-spin text-blue-400" />
            )}
            <span>{isDone ? doneText : loadingText}</span>
          </div>
        );
      }
      default:
        return null;
    }
  };

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
          status={(isTransitioningToInvestigation || isTransitioningFromPlanning) ? "active" : phaseState.investigation}
          defaultExpanded
          isLast
        >
          <div className="space-y-3">
            {hasInvestigations ? (
              // New architecture: interleave coordinator thinking + InvestigationCards
              scrollParent && mergedItems.length > 0 ? (
                <Virtuoso
                  customScrollParent={scrollParent}
                  data={mergedItems}
                  computeItemKey={(index, item) =>
                    item.kind === "investigation"
                      ? `inv-${item.inv.hypothesisId}`
                      : `tl-${item.idx}`
                  }
                  increaseViewportBy={{ top: 400, bottom: 400 }}
                  itemContent={(index, item) => (
                    <div className={index < mergedItems.length - 1 ? "pb-3" : ""}>
                      {item.kind === "investigation" ? (
                        <SubAgentCard
                          title={item.inv.hypothesisTitle}
                          events={item.inv.events}
                          status={item.inv.status}
                          isActive={item.inv.hypothesisId === activeInvestigationId}
                          streamingContent={item.inv.thinkingContent}
                          summary={item.inv.summary}
                          serverMap={serverMap}
                          serviceMap={serviceMap}
                          incidentStatus={incidentStatus}
                          forceExpanded={item.inv.hypothesisId === activeInvestigationId}
                        />
                      ) : (
                        renderTimelineItem(item.item, item.idx)
                      )}
                    </div>
                  )}
                />
              ) : (
                // Fallback: render without virtualization (scrollParent not ready or empty list)
                mergedItems.map((m, i) =>
                  m.kind === "investigation" ? (
                    <SubAgentCard
                      key={`inv-${m.inv.hypothesisId}`}
                      title={m.inv.hypothesisTitle}
                      events={m.inv.events}
                      status={m.inv.status}
                      isActive={m.inv.hypothesisId === activeInvestigationId}
                      streamingContent={m.inv.thinkingContent}
                      summary={m.inv.summary}
                      serverMap={serverMap}
                      serviceMap={serviceMap}
                      incidentStatus={incidentStatus}
                      forceExpanded={m.inv.hypothesisId === activeInvestigationId}
                    />
                  ) : (
                    <div key={`tl-${m.idx}`}>{renderTimelineItem(m.item, m.idx)}</div>
                  ),
                )
              )
            ) : totalRounds <= 1 ? (
              // Legacy: single round — virtualize flat list
              scrollParent && timelineItems.length > 0 ? (
                <Virtuoso
                  customScrollParent={scrollParent}
                  data={timelineItems}
                  computeItemKey={(index) => `tl-${index}`}
                  increaseViewportBy={{ top: 400, bottom: 400 }}
                  itemContent={(index, item) => (
                    <div className={index < timelineItems.length - 1 ? "pb-3" : ""}>
                      {renderTimelineItem(item, index)}
                    </div>
                  )}
                />
              ) : (
                timelineItems.map((item, i) => renderTimelineItem(item, i))
              )
            ) : (
              // Legacy: multiple rounds, group by round with expand/collapse
              Array.from(roundGrouped.entries()).map(([round, items]) => {
                const isCurrentRound = round === currentRound;
                const isExpanded = isCurrentRound || expandedRounds.has(round);
                const summaryEntry = roundSummaries.find((s) => s.round === round);
                const summaryText = summaryEntry?.summary || "";

                return (
                  <div key={`round-${round}`}>
                    {/* Round header */}
                    {isCurrentRound ? (
                      <div className="flex items-center gap-2 py-1.5 text-sm text-muted-foreground">
                        <div className="h-px w-4 bg-border" />
                        <span className="font-medium">第 {round} 轮</span>
                        <div className="h-px flex-1 bg-border" />
                      </div>
                    ) : (
                      <button
                        className="group flex w-full cursor-pointer items-center gap-2 py-1.5 text-left text-sm text-muted-foreground transition-colors"
                        onClick={() => toggleRound(round)}
                      >
                        <div className="h-px w-4 bg-border" />
                        <ChevronRight className={cn(
                          "h-3.5 w-3.5 shrink-0 transition-transform",
                          isExpanded && "rotate-90",
                        )} />
                        <span className="font-medium group-hover:text-foreground transition-colors">第 {round} 轮</span>
                        {!isExpanded && summaryText && (
                          <span className="truncate text-xs text-muted-foreground/70">
                            {summaryText.slice(0, 60)}...
                          </span>
                        )}
                        <div className="h-px flex-1 bg-border" />
                      </button>
                    )}

                    {/* Round content */}
                    {(isCurrentRound || isExpanded) && (
                      <div className="space-y-3 border-l-2 border-border/50 pl-4 ml-1.5">
                        {items.map((item, i) => renderTimelineItem(item, i))}
                      </div>
                    )}
                  </div>
                );
              })
            )}

            {/* Transitional indicator — waiting for first investigation event after context gathering */}
            {!hasInvestigations && (isTransitioningToInvestigation || isTransitioningFromPlanning) && timelineItems.length === 0 && !hasThinking && (
              <div className="px-1 py-2">
                <TextDotsLoader text="Agent 思考中" size="sm" />
              </div>
            )}

            {/* Waiting indicator — shown between tool_result and next LLM output */}
            {!hasInvestigations && <WaitingIndicator />}

            {/* Live thinking stream — isolated component to avoid re-rendering timeline */}
            {!hasInvestigations && <LiveThinkingSection />}

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
