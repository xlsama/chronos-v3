import { useState, useMemo, useEffect } from "react";

import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Search,
  BookOpen,
  FileText,
  Loader2,
  Wrench,
} from "lucide-react";
import type { SSEEvent } from "@/lib/types";
import { Markdown } from "@/components/ui/markdown";
import { cn, formatDuration } from "@/lib/utils";
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

interface Source {
  type: "incident_history" | "document";
  id: string;
  title?: string;
  filename?: string;
  page?: number;
}

const AGENT_CONFIG: Record<
  string,
  { label: string; icon: typeof Search; subAgentName: string }
> = {
  history: { label: "历史事件检索", icon: Search, subAgentName: "Incident History Subagent" },
  kb: { label: "知识库检索", icon: BookOpen, subAgentName: "KB Subagent" },
};

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

  return (
    <div className="rounded-lg border border-blue-200 bg-white/60 text-xs">
      <button
        className="flex w-full items-center gap-1.5 p-2 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-blue-400" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-blue-400" />
        )}
        <Wrench className="h-3 w-3 shrink-0 text-blue-600" />
        <span className="font-mono font-semibold text-blue-800">{name}</span>
        {isExecuting && (
          <Loader2 className="ml-auto h-3 w-3 animate-spin text-blue-500" />
        )}
      </button>
      {expanded && (
        <div className="space-y-1.5 border-t border-blue-100 p-2">
          {hasArgs && (
            <pre className="overflow-auto rounded border-l-2 border-blue-400 bg-background p-1.5 pl-3 text-xs shadow-sm">
              {JSON.stringify(args, null, 2)}
            </pre>
          )}
          {output && (
            <div className="max-h-40 overflow-auto rounded border-l-2 border-green-400 bg-background p-1.5 pl-3 text-xs shadow-sm">
              <Markdown content={output} variant="tiny" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface SubAgentCardProps {
  agentName: string;
  events: SSEEvent[];
  status: "idle" | "started" | "completed" | "failed";
  streamingContent?: string;
  forceExpanded?: boolean;
  fixedLayout?: boolean;
  className?: string;
}

export function SubAgentCard({
  agentName,
  events,
  status,
  streamingContent,
  forceExpanded,
  fixedLayout,
  className,
}: SubAgentCardProps) {
  const [localExpanded, setLocalExpanded] = useState(!!forceExpanded);

  useEffect(() => {
    if (forceExpanded) {
      setLocalExpanded(true);
    }
  }, [forceExpanded]);

  const expanded = localExpanded;

  const { scrollRef: scrollContainerRef } = useAutoScroll({
    enabled: forceExpanded,
    threshold: 50,
  });

  // Preview state
  const [previewSource, setPreviewSource] = useState<Source | null>(null);

  const hasEvents = events.length > 0 || !!streamingContent;
  const config = AGENT_CONFIG[agentName] ?? {
    label: agentName,
    icon: Search,
  };
  const Icon = config.icon;

  const { toolCallCount, duration } = useMemo(() => {
    const count = events.filter((e) => e.event_type === "tool_use").length;
    let dur = "";
    if (events.length >= 2) {
      dur = formatDuration(events[0].timestamp, events[events.length - 1].timestamp);
    }
    return { toolCallCount: count, duration: dur };
  }, [events]);

  const sources = useMemo(() => {
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
  }, [events]);

  const subAgentItems = useMemo(() => buildSubAgentItems(events), [events]);

  const statusText =
    status === "idle"
      ? "等待中..."
      : status === "started"
        ? "检索中..."
        : status === "failed"
          ? "检索失败"
          : [
            duration && duration !== "0s" ? duration : null,
            toolCallCount > 0 ? `${toolCallCount} 次调用` : null,
          ]
            .filter(Boolean)
            .join(" · ") || "完成";

  return (
    <div
      data-expanded={expanded || undefined}
      className={cn(
        "flex min-h-0 flex-col rounded-lg border",
        status === "failed"
          ? "border-red-200 bg-red-50/30"
          : "border-blue-200 bg-blue-50/50",
        fixedLayout && expanded && "flex-1 overflow-hidden",
        className,
      )}
      data-testid="sub-agent-card"
    >
      <button
        className="flex w-full items-center gap-2 p-3 text-left text-sm font-medium text-blue-800"
        onClick={() => setLocalExpanded(!localExpanded)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <Icon className="h-4 w-4" />
        <span>{config.label}</span>
        {"subAgentName" in config && (
          <span className="ml-1.5 rounded bg-blue-100 px-1 py-px text-[9px] font-normal text-blue-500">
            {config.subAgentName}
          </span>
        )}
        <span className="ml-auto text-xs text-blue-600">
          {statusText}
        </span>
      </button>

      {/* Sources row */}
      {status !== "started" && sources.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 px-3 pb-2 pl-9 text-xs text-blue-700">
          <FileText className="h-3 w-3 shrink-0 opacity-60" />
          {sources.map((s, i) => (
            <span key={s.id} className="inline-flex items-center">
              {i > 0 && <span className="mx-1 opacity-40">&middot;</span>}
              <button
                className="hover:text-blue-900 hover:underline"
                onClick={(e) => {
                  e.stopPropagation();
                  setPreviewSource(s);
                }}
              >
                {s.title || s.filename || s.id.slice(0, 8)}
              </button>
            </span>
          ))}
        </div>
      )}

      {expanded && (hasEvents || status === "started") && (
        <div
          className="flex-1 min-h-0 overflow-y-auto space-y-2 px-3 pb-3 pl-9 text-sm text-blue-900/80"
          ref={scrollContainerRef}
        >
          {status === "started" && !hasEvents && (
            <div className="space-y-4">
              <Skeleton className="h-3 w-11/12 bg-blue-200/50" />
              <Skeleton className="h-3 w-3/5 bg-blue-200/50" />
              <Skeleton className="h-3 w-4/5 bg-blue-200/50" />
              <Skeleton className="h-3 w-2/3 bg-blue-200/50" />
              <Skeleton className="h-3 w-5/6 bg-blue-200/50" />
              <Skeleton className="h-3 w-1/2 bg-blue-200/50" />
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

      {/* Preview dialogs */}
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
