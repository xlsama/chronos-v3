import { useState, useMemo, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
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
import { formatDuration } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getIncidentHistory } from "@/api/incident-history";
import { DocumentViewer } from "@/components/projects/document-viewer";

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
    } else if (event.event_type === "tool_call") {
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
            <pre className="overflow-auto rounded bg-blue-50/50 p-1.5 text-xs opacity-70">
              {JSON.stringify(args, null, 2)}
            </pre>
          )}
          {output && (
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-blue-50/50 p-1.5 text-xs opacity-70">
              {output}
            </pre>
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
}

export function SubAgentCard({
  agentName,
  events,
  status,
  streamingContent,
  forceExpanded,
}: SubAgentCardProps) {
  const [localExpanded, setLocalExpanded] = useState(false);
  const expanded = forceExpanded || localExpanded;
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Preview state
  const [previewSource, setPreviewSource] = useState<Source | null>(null);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      el.scrollTop = el.scrollHeight;
    });
    for (const child of el.children) {
      observer.observe(child);
    }
    return () => observer.disconnect();
  }, []);

  const hasEvents = events.length > 0 || !!streamingContent;
  const config = AGENT_CONFIG[agentName] ?? {
    label: agentName,
    icon: Search,
  };
  const Icon = config.icon;

  const { toolCallCount, duration } = useMemo(() => {
    const count = events.filter((e) => e.event_type === "tool_call").length;
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
    status === "started"
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
      className="rounded-lg border border-blue-200 bg-blue-50/50 p-3"
      data-testid="sub-agent-card"
    >
      <button
        className="flex w-full items-center gap-2 text-left text-sm font-medium text-blue-800"
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
          <span className="ml-1.5 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-normal text-blue-500">
            {config.subAgentName}
          </span>
        )}
        <span className="ml-auto text-xs text-blue-600">{statusText}</span>
      </button>

      {/* Sources row */}
      {status !== "started" && sources.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1 pl-6 text-xs text-blue-700">
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

      <AnimatePresence initial={false}>
        {expanded && hasEvents && (
        <motion.div
          className="mt-2 max-h-[300px] overflow-y-auto space-y-2 pl-6 text-sm text-blue-900/80"
          ref={scrollContainerRef}
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          {subAgentItems.map((item, i) => {
            if (item.type === "thinking") {
              return (
                <div key={i} className="text-xs opacity-80">
                  <Markdown content={item.event.data.content as string} variant="compact" />
                </div>
              );
            }
            return <SubAgentToolItem key={i} item={item} />;
          })}

          {status === "started" && streamingContent && (
            <div className="text-xs opacity-80 animate-pulse">
              <Markdown content={streamingContent} streaming variant="compact" />
            </div>
          )}
        </motion.div>
      )}
      </AnimatePresence>

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
      <DialogContent className="flex h-[80vh] flex-col sm:max-w-[70vw]">
        <DialogHeader>
          <DialogTitle className="truncate">
            {data?.title ?? "历史事件"}
          </DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : data ? (
            <Markdown content={data.summary_md} />
          ) : (
            <p className="text-muted-foreground">未找到历史记录</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
