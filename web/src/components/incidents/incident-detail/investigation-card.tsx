import { useState, useMemo } from "react";
import {
  ChevronDown,
  ChevronRight,
  Search,
  Check,
  X,
  Loader2,
  AlertTriangle,
  HelpCircle,
} from "lucide-react";
import { cn, formatDuration, formatRelativeTime } from "@/lib/utils";
import type { SSEEvent } from "@/lib/types";
import type { InvestigationSubAgent } from "@/stores/incident-stream";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { Markdown } from "@/components/ui/markdown";
import { TextDotsLoader } from "@/components/ui/loader";

interface InvestigationCardProps {
  investigation: InvestigationSubAgent;
  isActive: boolean;
  serverMap: Map<string, string>;
  serviceMap: Map<string, string>;
  incidentStatus?: string;
}

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
        if (name === "report_findings") break;
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
        if (name === "report_findings") break;
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

const STATUS_CONFIG = {
  running: {
    border: "border-l-blue-400",
    icon: Loader2,
    iconClass: "h-3.5 w-3.5 animate-spin text-blue-500",
    label: "排查中",
    labelClass: "text-blue-700 bg-blue-50 dark:text-blue-300 dark:bg-blue-950/50",
  },
  completed: {
    border: "border-l-gray-300",
    icon: Check,
    iconClass: "h-3.5 w-3.5 text-gray-500",
    label: "完成",
    labelClass: "text-gray-700 bg-gray-50 dark:text-gray-300 dark:bg-gray-800/50",
  },
  confirmed: {
    border: "border-l-green-400",
    icon: Check,
    iconClass: "h-3.5 w-3.5 text-green-600",
    label: "已确认",
    labelClass: "text-green-700 bg-green-50 dark:text-green-300 dark:bg-green-950/50",
  },
  eliminated: {
    border: "border-l-gray-300",
    icon: X,
    iconClass: "h-3.5 w-3.5 text-gray-400",
    label: "已排除",
    labelClass: "text-gray-500 bg-gray-50 dark:text-gray-400 dark:bg-gray-800/50",
  },
  failed: {
    border: "border-l-red-300",
    icon: AlertTriangle,
    iconClass: "h-3.5 w-3.5 text-red-500",
    label: "失败",
    labelClass: "text-red-700 bg-red-50 dark:text-red-300 dark:bg-red-950/50",
  },
} as const;

export function InvestigationCard({
  investigation,
  isActive,
  serverMap,
  serviceMap,
  incidentStatus,
}: InvestigationCardProps) {
  const { hypothesisId, hypothesisDesc, status, summary, events, thinkingContent } = investigation;
  const [userExpanded, setUserExpanded] = useState<boolean | null>(null);
  const expanded = userExpanded ?? isActive;

  const config = STATUS_CONFIG[status] || STATUS_CONFIG.running;
  const StatusIcon = config.icon;

  const cardItems = useMemo(() => buildCardItems(events), [events]);

  const { duration, toolCallCount } = useMemo(() => {
    const count = events.filter((e) => e.event_type === "tool_use").length;
    let dur = "";
    if (events.length >= 2) {
      dur = formatDuration(events[0].timestamp, events[events.length - 1].timestamp);
    }
    return { duration: dur, toolCallCount: count };
  }, [events]);

  const baseTimestamp = events.length > 0 ? events[0].timestamp : "";

  const statsText = [
    duration && duration !== "0s" ? duration : null,
    toolCallCount > 0 ? `${toolCallCount} 次调用` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      className={cn(
        "rounded-lg border border-l-2 transition-colors",
        config.border,
        status === "running" ? "border-border/80 bg-card" : "border-border/60 bg-card/80",
      )}
    >
      {/* Header */}
      <button
        className="flex w-full items-center gap-2 p-3 text-left text-sm"
        onClick={() => setUserExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="font-mono text-xs font-semibold text-muted-foreground">{hypothesisId}</span>
        <span className="font-medium truncate">{hypothesisDesc}</span>

        <span className="ml-auto flex shrink-0 items-center gap-2">
          {statsText && (
            <span className="text-xs text-muted-foreground">{statsText}</span>
          )}
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
              config.labelClass,
            )}
          >
            <StatusIcon className={config.iconClass} />
            {config.label}
          </span>
        </span>
      </button>

      {/* Collapsed summary preview */}
      {!expanded && summary && (
        <div className="border-t border-border/40 px-3 py-2 pl-11">
          <p className="truncate text-xs text-muted-foreground">{summary}</p>
        </div>
      )}

      {/* Expanded content */}
      {expanded && (
        <div className="space-y-3 border-t border-border/40 px-3 pb-3 pt-2 pl-11">
          {cardItems.map((item, i) => {
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
                  const sid = toolArgs?.server_id as string | undefined;
                  serverInfo = sid ? serverMap.get(sid) : undefined;
                } else if (toolName === "service_exec") {
                  const sid = toolArgs?.service_id as string | undefined;
                  serviceInfo = sid ? serviceMap.get(sid) : undefined;
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
                const ad = item.approvalEvent.data;
                const atn = (ad.tool_name as string) || "";
                const aa = ad.tool_args as Record<string, unknown> | undefined;
                let asi: string | undefined;
                let aSvcI: string | undefined;
                if (atn === "ssh_bash") asi = aa?.server_id ? serverMap.get(aa.server_id as string) : undefined;
                else if (atn === "service_exec") aSvcI = aa?.service_id ? serviceMap.get(aa.service_id as string) : undefined;
                return (
                  <div key={i}>
                    <ToolCallCard
                      name={atn}
                      args={aa}
                      output={item.toolResult?.data.output as string | undefined}
                      isExecuting={!!item.toolCall && !item.toolResult}
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
              case "skill_read":
                return null; // Skip skill_read in investigation cards for brevity
              default:
                return null;
            }
          })}

          {/* Live thinking stream */}
          {isActive && thinkingContent && (
            <div className="animate-in fade-in duration-150">
              <ThinkingBubble content={thinkingContent} isStreaming />
            </div>
          )}

          {/* Waiting indicator */}
          {isActive && !thinkingContent && events.length > 0 && (
            <div className="px-1 py-1">
              <TextDotsLoader text="Agent 思考中" size="sm" />
            </div>
          )}

          {/* Summary from report_findings */}
          {summary && status !== "running" && (
            <div className="rounded-lg border border-blue-100 bg-blue-50/30 p-3 dark:border-blue-800 dark:bg-blue-950/30">
              <p className="text-xs font-medium text-blue-800 mb-1 dark:text-blue-200">调查发现</p>
              <Markdown content={summary} variant="compact" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
