import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageCircleQuestion, CheckCircle, ListTodo, Check, Loader2, ChevronRight } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Virtuoso } from "react-virtuoso";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import type { InvestigationAgent } from "@/stores/incident-stream";
import { confirmResolution } from "@/api/incidents";
import { Button } from "@/components/ui/button";
import { getServers } from "@/api/servers";
import { getServices } from "@/api/services";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { SSEEvent } from "@/lib/types";
import { Markdown } from "@/components/ui/markdown";
import { TextDotsLoader } from "@/components/ui/loader";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { SkillReadCard } from "./skill-read-card";
import { AgentCard } from "./agent-card";
import { TimelineDivider } from "./timeline-divider";
import { UserMessageBubble } from "./user-message-bubble";
import { AnswerCard } from "./answer-card";

// --- Types ---

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
  | { kind: "investigation"; inv: InvestigationAgent; ts: string };

// --- Helpers ---

function buildTimelineItems(events: SSEEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  const pendingTools = new Map<string, number>();
  const pendingApprovals = new Map<string, number>();
  let pendingRoundIdx: number | undefined;
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
        currentRound++;
        break;
      case "tool_use": {
        const name = event.data.name as string;
        if (name === "complete") break;
        const callId = (event.data.tool_call_id as string) || `${name}_${idx}`;
        const approvalId = event.data.approval_id as string | undefined;

        const approvalIdx = approvalId ? pendingApprovals.get(approvalId) : undefined;
        if (approvalIdx !== undefined) {
          const item = items[approvalIdx] as {
            type: "approval_tool";
            approvalEvent: SSEEvent;
            toolCall?: SSEEvent;
            toolResult?: SSEEvent;
          };
          item.toolCall = event;
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
        break;
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

// --- Small isolated components ---

function WaitingIndicator() {
  const showWaiting = useIncidentStreamStore((s) => {
    if (!s.isWaitingForAgent) return false;
    // Triage 阶段的等待指示器在 ContextGatheringPhase 中渲染
    if (s.askHumanPhase === "gather_context") return false;
    // 有待处理的审批时不显示（Agent 在等审批，不是在思考）
    return !s.events.some(
      (e) =>
        e.event_type === "approval_required" &&
        e.data.approval_id &&
        !s.decidedApprovals[e.data.approval_id as string],
    );
  });
  if (!showWaiting) return null;
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
  const askHumanPhase = useIncidentStreamStore((s) => s.askHumanPhase);
  // Triage ask_human 在 ContextGatheringPhase 中渲染
  if (!askHumanStreamContent || askHumanPhase === "gather_context") return null;
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
  const [displayed, setDisplayed] = useState("");
  const displayedLenRef = useRef(0);
  const sourceRef = useRef("");
  const rafRef = useRef<number>();

  sourceRef.current = answerContent;

  const isActive = answerContent.length > 0;

  useEffect(() => {
    if (!isActive) {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = undefined;
      }
      displayedLenRef.current = 0;
      setDisplayed("");
      return;
    }

    const tick = () => {
      const src = sourceRef.current;
      if (!src) {
        rafRef.current = undefined;
        return;
      }

      if (displayedLenRef.current < src.length) {
        const remaining = src.length - displayedLenRef.current;
        const step = Math.max(8, Math.ceil(remaining / 3));
        displayedLenRef.current = Math.min(src.length, displayedLenRef.current + step);
        setDisplayed(src.slice(0, displayedLenRef.current));
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = undefined;
      }
    };
  }, [isActive]);

  if (!displayed) return null;
  return (
    <div className="animate-in fade-in duration-150">
      <AnswerCard content={displayed} isStreaming />
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

// --- Main Component ---

interface InvestigationPhaseProps {
  incidentId: string;
  incidentStatus?: string;
  scrollParent?: HTMLDivElement | null;
  isTransitioning: boolean;
}

export function InvestigationPhase({
  incidentId,
  incidentStatus,
  scrollParent,
  isTransitioning,
}: InvestigationPhaseProps) {
  const events = useIncidentStreamStore((s) => s.events);
  const allInvestigations = useIncidentStreamStore((s) => s.investigations);
  const activeInvestigationIds = useIncidentStreamStore((s) => s.activeInvestigationIds);
  const hasThinking = useIncidentStreamStore((s) => !!s.thinkingContent);
  const investigations = useMemo(
    () => allInvestigations.filter((i) => i.hypothesisId !== "VERIFY"),
    [allInvestigations],
  );
  const hasInvestigations = investigations.length > 0;

  const { data: serversData } = useQuery({
    queryKey: ["servers", "all"],
    queryFn: () => getServers({ page_size: 200 }),
    staleTime: 5 * 60 * 1000,
  });

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

  const timelineItems = useMemo(() => buildTimelineItems(events), [events]);

  const currentRound = useIncidentStreamStore((s) => s.currentRound);
  const roundSummaries = useIncidentStreamStore((s) => s.roundSummaries);

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

  const baseTimestamp = events.length > 0 ? events[0].timestamp : "";


  const mergedItems = useMemo((): MergedItem[] => {
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

    if (hasInvestigations) {
      merged.sort((a, b) => {
        if (!a.ts && !b.ts) return 0;
        if (!a.ts) return 1;
        if (!b.ts) return -1;
        return a.ts.localeCompare(b.ts);
      });
    }

    return merged;
  }, [timelineItems, investigations, hasInvestigations]);

  const renderInvestigationCard = (inv: InvestigationAgent) => (
    <AgentCard
      title={inv.hypothesisTitle}
      events={inv.events}
      status={inv.status}
      isActive={activeInvestigationIds.has(inv.hypothesisId)}
      isReporting={inv.isReporting}
      streamingContent={inv.thinkingContent}
      summary={inv.summary}
      serverMap={serverMap}
      serviceMap={serviceMap}
      incidentStatus={incidentStatus}
      forceExpanded={activeInvestigationIds.has(inv.hypothesisId)}
    />
  );

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
      case "ask_human": {
        const askData = item.event.data;
        const hasStructured = !!(askData.known_context || askData.assessment);
        return (
          <div key={i}>
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
              <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-200">Agent 需要更多信息</p>
                {hasStructured && (
                  <div className="mt-2 space-y-2">
                    {askData.known_context && (
                      <div className="rounded-md bg-gray-100/80 px-3 py-2 dark:bg-gray-800/50">
                        <p className="text-xs font-medium text-gray-500 dark:text-gray-400">已有信息</p>
                        <Markdown content={askData.known_context as string} variant="compact" className="mt-0.5 card-markdown text-xs" />
                      </div>
                    )}
                    {askData.assessment && (
                      <div className="rounded-md bg-blue-50/80 px-3 py-2 dark:bg-blue-950/30">
                        <p className="text-xs font-medium text-blue-600 dark:text-blue-400">初步判断</p>
                        <Markdown content={askData.assessment as string} variant="compact" className="mt-0.5 card-markdown text-xs" />
                      </div>
                    )}
                  </div>
                )}
                <Markdown
                  content={askData.question as string}
                  variant="compact"
                  className="mt-2 card-markdown card-markdown--amber"
                />
              </div>
            </div>
          </div>
        );
      }
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
    <div className="space-y-3">
      {totalRounds > 1 && !hasInvestigations ? (
        Array.from(roundGrouped.entries()).map(([round, items]) => {
          const isCurrentRound = round === currentRound;
          const isExpanded = isCurrentRound || expandedRounds.has(round);
          const summaryEntry = roundSummaries.find((s) => s.round === round);
          const summaryText = summaryEntry?.summary || "";

          return (
            <div key={`round-${round}`}>
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

              {(isCurrentRound || isExpanded) && (
                <div className="space-y-3 border-l-2 border-border/50 pl-4 ml-1.5">
                  {items.map((item, i) => renderTimelineItem(item, i))}
                </div>
              )}
            </div>
          );
        })
      ) : scrollParent && mergedItems.length > 0 ? (
        <Virtuoso
          customScrollParent={scrollParent}
          data={mergedItems}
          computeItemKey={(_index, item) =>
            item.kind === "investigation"
              ? `inv-${item.inv.hypothesisId}`
              : `tl-${item.idx}`
          }
          increaseViewportBy={{ top: 400, bottom: 400 }}
          itemContent={(index, item) => (
            <div className={index < mergedItems.length - 1 ? "pb-3" : ""}>
              {item.kind === "investigation"
                ? renderInvestigationCard(item.inv)
                : renderTimelineItem(item.item, item.idx)}
            </div>
          )}
        />
      ) : (
        mergedItems.map((m) =>
          m.kind === "investigation" ? (
            <div key={`inv-${m.inv.hypothesisId}`}>
              {renderInvestigationCard(m.inv)}
            </div>
          ) : (
            <div key={`tl-${m.idx}`}>{renderTimelineItem(m.item, m.idx)}</div>
          ),
        )
      )}

      {!hasInvestigations && isTransitioning && timelineItems.length === 0 && !hasThinking && (
        <div className="px-1 py-2">
          <TextDotsLoader text="Agent 思考中" size="sm" />
        </div>
      )}

      {!hasInvestigations && <WaitingIndicator />}
      {!hasInvestigations && <LiveThinkingSection />}
      <LiveAskHumanSection />
      <LiveAnswerSection />
      <ResolutionConfirmCard incidentId={incidentId} incidentStatus={incidentStatus} />
    </div>
  );
}
