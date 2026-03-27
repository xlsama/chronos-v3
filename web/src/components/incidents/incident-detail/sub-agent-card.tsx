import { useState, useMemo } from "react";

import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Search,
  BookOpen,
  FileText,
  Loader2,
  Wrench,
  Bug,
  History,
  Check,
  X,
  AlertTriangle,
  HelpCircle,
} from "lucide-react";
import type { SSEEvent } from "@/lib/types";
import { Markdown } from "@/components/ui/markdown";
import { cn, formatDuration, formatRelativeTime } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getIncidentHistory } from "@/api/incident-history";
import { DocumentViewer } from "@/components/projects/document-viewer";
import { ScrollArea } from "@/components/ui/scroll-area";
import { QueryContent } from "@/components/query-content";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { SkillReadCard } from "./skill-read-card";
import { TextDotsLoader } from "@/components/ui/loader";
import { TextShimmer } from "@/components/ui/text-shimmer";


// ─── Types ───────────────────────────────────────────────

interface Source {
  type: "incident_history" | "document";
  id: string;
  title?: string;
  filename?: string;
  page?: number;
}

type SubAgentStatus =
  | "idle" | "started" | "completed" | "failed"
  | "running" | "confirmed" | "eliminated" | "cancelled";

// ─── Agent config (context gathering mode) ───────────────

const AGENT_CONFIG: Record<
  string,
  { label: string; icon: typeof Search; subAgentName: string }
> = {
  history: { label: "历史事件检索", icon: History, subAgentName: "Incident History Subagent" },
  kb: { label: "知识库检索", icon: BookOpen, subAgentName: "KB Subagent" },
};

// ─── Investigation status config ─────────────────────────

const STATUS_CONFIG: Record<string, {
  icon: typeof Check;
  iconClass: string;
  label: string;
  labelClass: string;
}> = {
  running: {
    icon: Loader2,
    iconClass: "h-3 w-3 animate-spin",
    label: "排查中",
    labelClass: "text-blue-700 bg-blue-50 dark:text-blue-300 dark:bg-blue-950/50",
  },
  completed: {
    icon: Check,
    iconClass: "h-3 w-3 text-gray-500",
    label: "完成",
    labelClass: "text-gray-700 bg-gray-50 dark:text-gray-300 dark:bg-gray-800/50",
  },
  confirmed: {
    icon: Check,
    iconClass: "h-3 w-3 text-green-600",
    label: "已确认",
    labelClass: "text-green-700 bg-green-50 dark:text-green-300 dark:bg-green-950/50",
  },
  eliminated: {
    icon: X,
    iconClass: "h-3 w-3 text-gray-400",
    label: "已排除",
    labelClass: "text-gray-500 bg-gray-50 dark:text-gray-400 dark:bg-gray-800/50",
  },
  failed: {
    icon: AlertTriangle,
    iconClass: "h-3 w-3 text-red-500",
    label: "失败",
    labelClass: "text-red-700 bg-red-50 dark:text-red-300 dark:bg-red-950/50",
  },
  cancelled: {
    icon: X,
    iconClass: "h-3 w-3 text-gray-400",
    label: "已取消",
    labelClass: "text-gray-500 bg-gray-50 dark:text-gray-400 dark:bg-gray-800/50",
  },
};

// ─── Context gathering: item builders ────────────────────

interface PairedTool {
  type: "paired_tool";
  toolCall: SSEEvent;
  toolResult?: SSEEvent;
}
interface ThinkingItem {
  type: "thinking";
  event: SSEEvent;
}
type SubAgentItem = PairedTool | ThinkingItem;

function buildSubAgentItems(events: SSEEvent[]): SubAgentItem[] {
  const items: SubAgentItem[] = [];
  const pendingTools = new Map<string, number>();

  for (const event of events) {
    if (event.event_type === "thinking") {
      items.push({ type: "thinking", event });
    } else if (event.event_type === "tool_use") {
      const name = event.data.name as string;
      items.push({ type: "paired_tool", toolCall: event });
      pendingTools.set(name, items.length - 1);
    } else if (event.event_type === "tool_result") {
      const name = event.data.name as string;
      const idx = pendingTools.get(name);
      if (idx !== undefined) {
        (items[idx] as PairedTool).toolResult = event;
        pendingTools.delete(name);
      }
    }
  }
  return items;
}

function SubAgentToolItem({ item }: { item: PairedTool }) {
  const [expanded, setExpanded] = useState(!item.toolResult);
  const name = item.toolCall.data.name as string;
  const args = item.toolCall.data.args as Record<string, unknown> | undefined;
  const output = item.toolResult?.data.output as string | undefined;
  const hasArgs = args && Object.keys(args).length > 0;
  const isExecuting = !item.toolResult;
  const status = item.toolResult?.data.status as "success" | "error" | undefined;

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/50 text-xs dark:border-blue-500/15 dark:bg-blue-500/[0.06]">
      <button
        className="flex w-full items-center gap-1.5 p-2 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-blue-400 dark:text-blue-400/60" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-blue-400 dark:text-blue-400/60" />
        )}
        {isExecuting ? (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin text-blue-500" />
        ) : (
          <Wrench className={cn("h-3 w-3 shrink-0", status === "error" ? "text-orange-500 dark:text-orange-400" : "text-blue-600 dark:text-blue-400")} />
        )}
        <span className="font-mono font-semibold text-blue-800 dark:text-blue-200">{name}</span>
        {isExecuting && (
          <TextDotsLoader text="执行中" size="sm" className="ml-auto text-muted-foreground" />
        )}
        {!isExecuting && status === "error" && (
          <span className="ml-auto inline-block rounded px-1.5 py-0.5 text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300">
            失败
          </span>
        )}
      </button>
      {expanded && (
        <div className="space-y-2 border-t border-blue-100 p-2 dark:border-blue-500/10">
          {hasArgs && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Input</p>
              <pre className="overflow-auto rounded-md border border-border/50 bg-background px-3 py-1.5 text-xs">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}
          {output && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Output</p>
              <div className="max-h-40 overflow-auto rounded-md border border-border/50 bg-background px-3 py-1.5 text-xs">
                <Markdown content={output} variant="tiny" />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Investigation: item builders ────────────────────────

type CardItem =
  | { type: "thinking"; event: SSEEvent }
  | { type: "paired_tool"; toolCall: SSEEvent; toolResult?: SSEEvent }
  | { type: "approval_tool"; approvalEvent: SSEEvent; toolCall?: SSEEvent; toolResult?: SSEEvent }
  | { type: "ask_human"; event: SSEEvent }
  | { type: "error"; event: SSEEvent }
  | { type: "skill_read"; event: SSEEvent };

function buildCardItems(events: SSEEvent[]): CardItem[] {
  const items: CardItem[] = [];
  const pendingTools = new Map<string, number>();
  const pendingApprovals = new Map<string, number>();

  for (const [idx, event] of events.entries()) {
    switch (event.event_type) {
      case "thinking":
        items.push({ type: "thinking", event });
        break;
      case "tool_use": {
        const name = event.data.name as string;
        if (name === "report") break;
        const callId = (event.data.tool_call_id as string) || `${name}_${idx}`;
        const approvalId = event.data.approval_id as string | undefined;
        const approvalIdx = approvalId ? pendingApprovals.get(approvalId) : undefined;
        if (approvalIdx !== undefined) {
          const item = items[approvalIdx] as { toolCall?: SSEEvent };
          item.toolCall = event;
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
        if (name === "report") break;
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
        if (approvalId) pendingApprovals.set(approvalId, itemIdx);
        break;
      }
      case "ask_human":
        items.push({ type: "ask_human", event });
        break;
      case "error":
        items.push({ type: "error", event });
        break;
      case "skill_read":
        if (event.data.success !== false) {
          items.push({ type: "skill_read", event });
        }
        break;
      default:
        break;
    }
  }
  return items;
}

// ─── Unified SubAgentCard ────────────────────────────────

interface SubAgentCardProps {
  events: SSEEvent[];
  status: SubAgentStatus;
  className?: string;
  forceExpanded?: boolean;
  fixedLayout?: boolean;
  streamingContent?: string;

  // Context gathering mode (activated when agentName is provided)
  agentName?: string;

  // Investigation mode (activated when agentName is absent)
  title?: string;
  summary?: string;
  isActive?: boolean;
  serverMap?: Map<string, string>;
  serviceMap?: Map<string, string>;
  incidentStatus?: string;
}

export function SubAgentCard({
  events,
  status,
  className,
  forceExpanded,
  fixedLayout,
  streamingContent,
  agentName,
  title,
  summary,
  isActive,
  serverMap,
  serviceMap,
  incidentStatus,
}: SubAgentCardProps) {
  const isContextGathering = !!agentName;

  const [userExpanded, setUserExpanded] = useState<boolean | null>(
    forceExpanded ? true : null,
  );
  const expanded = forceExpanded || (userExpanded ?? (isActive || false));

  const { scrollRef: scrollContainerRef } = useAutoScroll({
    enabled: forceExpanded,
    threshold: 50,
  });

  // Preview state (context gathering only)
  const [previewSource, setPreviewSource] = useState<Source | null>(null);

  const hasEvents = events.length > 0 || !!streamingContent;

  // Resolve config for context gathering
  const agentConfig = agentName ? AGENT_CONFIG[agentName] : undefined;
  const Icon = agentConfig?.icon ?? Bug;
  const isLoading = status === "started" || status === "running";

  // Stats
  const { toolCallCount, duration } = useMemo(() => {
    const count = events.filter((e) => e.event_type === "tool_use").length;
    let dur = "";
    if (events.length >= 2) {
      dur = formatDuration(events[0].timestamp, events[events.length - 1].timestamp);
    }
    return { toolCallCount: count, duration: dur };
  }, [events]);

  // Sources (context gathering only)
  const sources = useMemo(() => {
    if (!isContextGathering) return [];
    const all: Source[] = [];
    const seen = new Set<string>();
    for (const e of events) {
      if (e.event_type === "tool_result" && Array.isArray(e.data.sources)) {
        for (const s of e.data.sources as Source[]) {
          if (!seen.has(s.id)) {
            seen.add(s.id);
            all.push(s);
          }
        }
      }
    }
    return all;
  }, [events, isContextGathering]);

  // Build items per mode
  const subAgentItems = useMemo(
    () => (isContextGathering ? buildSubAgentItems(events) : []),
    [events, isContextGathering],
  );
  const cardItems = useMemo(
    () => (isContextGathering ? [] : buildCardItems(events)),
    [events, isContextGathering],
  );

  // Status text for right side (loading status is shown on the left now)
  const statsText = (() => {
    if (isContextGathering && status === "failed") return "检索失败";
    if (isLoading) return "";
    const parts = [
      duration && duration !== "0s" ? duration : null,
      toolCallCount > 0 ? `${toolCallCount} 次调用` : null,
    ].filter(Boolean).join(" · ");
    return parts || (isContextGathering ? "完成" : "");
  })();

  // Investigation status badge config
  const statusBadge = !isContextGathering ? STATUS_CONFIG[status] : undefined;

  // Base timestamp for relative time in investigation mode
  const baseTimestamp = events.length > 0 ? events[0].timestamp : "";

  return (
    <div
      data-expanded={expanded || undefined}
      className={cn(
        "flex min-h-0 flex-col rounded-lg border",
        status === "failed"
          ? "border-red-200 bg-red-50/30 dark:border-red-800 dark:bg-red-950/30"
          : "border-border/60 bg-card",
        fixedLayout && expanded && "flex-1 overflow-hidden",
        className,
      )}
      data-testid="sub-agent-card"
    >
      {/* Header */}
      <button
        className="flex w-full items-center gap-2 p-3 text-left text-sm font-medium text-foreground"
        onClick={() => setUserExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0" />
        )}
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
        {isLoading ? (
          <TextShimmer className="truncate font-medium" duration={2}>
            {isContextGathering ? agentConfig?.label ?? agentName : title}
          </TextShimmer>
        ) : (
          <span className="truncate font-medium">
            {isContextGathering ? agentConfig?.label ?? agentName : title}
          </span>
        )}

        {/* Badge: subAgentName (context) or investigation badge */}
        {isContextGathering && agentConfig?.subAgentName && (
          <span className="ml-1.5 shrink-0 rounded bg-muted px-1 py-px text-[9px] font-normal text-muted-foreground">
            {agentConfig.subAgentName}
          </span>
        )}
        {!isContextGathering && (
          <span className="ml-1.5 shrink-0 rounded bg-muted px-1 py-px text-[9px] font-normal text-muted-foreground">
            Investigation Subagent
          </span>
        )}
        {!isLoading && statusBadge && (
          <span
            className={cn(
              "ml-1.5 inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
              statusBadge.labelClass,
            )}
          >
            {(() => {
              const BadgeIcon = statusBadge.icon;
              return <BadgeIcon className={statusBadge.iconClass} />;
            })()}
            {statusBadge.label}
          </span>
        )}

        {/* Right side: loading indicator / sources / stats */}
        <span className="ml-auto inline-flex shrink-0 items-center gap-4">
          {isLoading && (
            <span className="inline-flex items-center gap-1.5 text-blue-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <TextDotsLoader
                className="text-blue-500"
                text={isContextGathering
                  ? status === "idle" ? "等待中" : "检索中"
                  : statusBadge?.label ?? "排查中"}
                size="sm"
              />
            </span>
          )}
          {isContextGathering && !isLoading && sources.length > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-normal text-muted-foreground">
              <FileText className="h-3 w-3 shrink-0 opacity-60" />
              {sources.map((s, i) => (
                <span key={s.id} className="inline-flex shrink-0 items-center">
                  {i > 0 && <span className="mx-0.5 opacity-40">&middot;</span>}
                  <span
                    role="button"
                    tabIndex={0}
                    className="cursor-pointer hover:text-foreground hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPreviewSource(s);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.stopPropagation();
                        setPreviewSource(s);
                      }
                    }}
                  >
                    {s.title || s.filename || s.id.slice(0, 8)}
                  </span>
                </span>
              ))}
            </span>
          )}
          {statsText && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {statsText}
            </span>
          )}
        </span>
      </button>

      {/* Collapsed summary preview (investigation only) */}
      {!expanded && !isContextGathering && summary && (
        <div className="border-t border-border/40 px-3 py-2 pl-11">
          <p className="truncate text-xs text-muted-foreground">{summary}</p>
        </div>
      )}

      {/* Expanded content: context gathering mode */}
      {expanded && isContextGathering && (hasEvents || status === "started") && (
        <div
          className="flex-1 min-h-0 overflow-y-auto space-y-2 px-3 pb-3 pl-9 text-sm text-foreground/80"
          ref={scrollContainerRef}
        >
          {status === "started" && !hasEvents && (
            <div className="space-y-4">
              <Skeleton className="h-3 w-11/12 bg-muted/50" />
              <Skeleton className="h-3 w-3/5 bg-muted/50" />
              <Skeleton className="h-3 w-4/5 bg-muted/50" />
              <Skeleton className="h-3 w-2/3 bg-muted/50" />
              <Skeleton className="h-3 w-5/6 bg-muted/50" />
              <Skeleton className="h-3 w-1/2 bg-muted/50" />
            </div>
          )}
          {subAgentItems.map((item, i) => {
            if (item.type === "thinking") {
              return (
                <div key={i} className="text-xs opacity-80">
                  <Markdown content={item.event.data.content as string} variant="tiny" />
                </div>
              );
            }
            return <SubAgentToolItem key={i} item={item} />;
          })}

          {status === "started" && streamingContent && (
            <div className="text-xs opacity-80">
              <Markdown content={streamingContent} streaming variant="tiny" />
            </div>
          )}
        </div>
      )}

      {/* Expanded content: investigation mode */}
      {expanded && !isContextGathering && (
        <div className="space-y-3 border-t border-border/40 px-3 pb-3 pt-2 pl-11">
          {/* Skeleton loading state */}
          {isActive && status === "running" && !hasEvents && (
            <div className="animate-in fade-in duration-200 space-y-4 min-h-[100px]">
              <Skeleton className="h-3 w-3/5 bg-muted/50" />
              <Skeleton className="h-3 w-4/5 bg-muted/50" />
              <Skeleton className="h-3 w-1/2 bg-muted/50" />
            </div>
          )}
          {cardItems.map((item, i) => {
            switch (item.type) {
              case "thinking":
                return (
                  <div key={i} className="animate-in fade-in slide-in-from-bottom-1 duration-200">
                    <ThinkingBubble content={item.event.data.content as string} />
                  </div>
                );
              case "paired_tool": {
                const toolName = item.toolCall.data.name as string;
                const toolArgs = item.toolCall.data.args as Record<string, unknown> | undefined;
                let serverInfo: string | undefined;
                let serviceInfo: string | undefined;
                if (toolName === "ssh_bash") {
                  const sid = toolArgs?.server_id as string | undefined;
                  serverInfo = sid ? serverMap?.get(sid) : undefined;
                } else if (toolName === "service_exec") {
                  const sid = toolArgs?.service_id as string | undefined;
                  serviceInfo = sid ? serviceMap?.get(sid) : undefined;
                }
                const relTime = baseTimestamp
                  ? formatRelativeTime(item.toolCall.timestamp, baseTimestamp)
                  : undefined;
                return (
                  <div key={i} className="animate-in fade-in slide-in-from-bottom-1 duration-200">
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
                const ad = item.approvalEvent.data;
                const atn = (ad.tool_name as string) || "";
                const aa = ad.tool_args as Record<string, unknown> | undefined;
                let asi: string | undefined;
                let aSvcI: string | undefined;
                if (atn === "ssh_bash") asi = aa?.server_id ? serverMap?.get(aa.server_id as string) : undefined;
                else if (atn === "service_exec") aSvcI = aa?.service_id ? serviceMap?.get(aa.service_id as string) : undefined;
                return (
                  <div key={i} className="animate-in fade-in slide-in-from-bottom-1 duration-200">
                    <ToolCallCard
                      name={atn}
                      args={aa}
                      output={item.toolResult?.data.output as string | undefined}
                      isExecuting={!!item.toolCall && !item.toolResult}
                      status={item.toolResult?.data.status as "success" | "error" | undefined}
                      serverInfo={asi}
                      serviceInfo={aSvcI}
                      approvalId={ad.approval_id as string}
                      riskLevel={aa?.risk_level as string | undefined}
                      explanation={aa?.explanation as string | undefined}
                      incidentStatus={incidentStatus}
                    />
                  </div>
                );
              }
              case "ask_human":
                return (
                  <div key={i} className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-3">
                    <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                    <div>
                      <p className="text-xs font-medium text-amber-800">需要更多信息</p>
                      <Markdown
                        content={item.event.data.question as string}
                        variant="compact"
                        className="mt-1 card-markdown card-markdown--amber"
                      />
                    </div>
                  </div>
                );
              case "error":
                return (
                  <div key={i} className="rounded-md border border-destructive bg-destructive/10 p-3">
                    <Markdown
                      content={item.event.data.message as string}
                      variant="compact"
                      className="card-markdown card-markdown--destructive"
                    />
                  </div>
                );
              case "skill_read": {
                const sName = item.event.data.skill_name as string;
                const sSlug = (item.event.data.skill_slug as string) || sName;
                return <SkillReadCard key={i} skillName={sName} skillSlug={sSlug} />;
              }
              default:
                return null;
            }
          })}

          {/* Live thinking stream */}
          {isActive && streamingContent && (
            <div className="animate-in fade-in duration-150">
              <ThinkingBubble content={streamingContent} isStreaming />
            </div>
          )}

          {/* Waiting indicator */}
          {isActive && !streamingContent && events.length > 0 && (
            <div className="px-1 py-1">
              <TextDotsLoader text="Agent 思考中" size="sm" />
            </div>
          )}

          {/* Summary from report */}
          {summary && status !== "running" && (
            <Markdown content={summary} variant="compact" />
          )}
        </div>
      )}

      {/* Preview dialogs (context gathering only) */}
      {previewSource?.type === "incident_history" && (
        <IncidentHistoryPreview
          id={previewSource.id}
          onClose={() => setPreviewSource(null)}
        />
      )}
      {previewSource?.type === "document" && (
        <DocumentViewer
          documentId={previewSource.id}
          onClose={() => setPreviewSource(null)}
          readOnly
        />
      )}
    </div>
  );
}

function IncidentHistoryPreview({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["incident-history", id],
    queryFn: () => getIncidentHistory(id),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex h-[80vh] flex-col overflow-hidden sm:max-w-[70vw]">
        <DialogHeader>
          <DialogTitle className="truncate">
            {data?.title ?? "历史事件"}
          </DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1">
          <QueryContent
            className="h-full"
            isLoading={isLoading}
            data={data}
            skeleton={
              <div className="space-y-3 p-4">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            }
            empty={<p className="p-4 text-muted-foreground">未找到历史记录</p>}
          >
            {(data) => (
              <ScrollArea className="h-full" scrollToTop>
                <div className="p-4">
                  <Markdown content={data.summary_md} />
                </div>
              </ScrollArea>
            )}
          </QueryContent>
        </div>
      </DialogContent>
    </Dialog>
  );
}
