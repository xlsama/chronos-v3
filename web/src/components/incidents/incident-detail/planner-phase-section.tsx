import { useState, type ReactNode } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { Markdown } from "@/components/ui/markdown";
import { TextDotsLoader } from "@/components/ui/loader";

const STATUS_BADGE_MAP: Record<string, string> = {
  "待验证": "badge-pending",
  "排查中": "badge-investigating",
  "已确认": "badge-confirmed",
  "已排除": "badge-eliminated",
};

const STATUS_RE = /^(H\d+)\s+\[(待验证|排查中|已确认|已排除)\]\s*(.*)/s;

function extractText(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(extractText).join("");
  return "";
}

const PLAN_COMPONENTS = {
  h3: ({ children, node: _, ...props }: React.ComponentProps<"h3"> & { node?: unknown }) => {
    const text = extractText(children);
    const match = text.match(STATUS_RE);
    if (match) {
      const [, id, status, desc] = match;
      return (
        <h3 {...props}>
          {id}{" "}
          <span className={`hypothesis-badge ${STATUS_BADGE_MAP[status]}`}>{status}</span>{" "}
          {desc}
        </h3>
      );
    }
    return <h3 {...props}>{children}</h3>;
  },
};

export function PlannerContent() {
  const planMd = useIncidentStreamStore((s) => s.plannerPlanMd);
  const thinkingContent = useIncidentStreamStore((s) => s.plannerThinkingContent);
  const planningStatus = useIncidentStreamStore((s) => s.phaseState.planning);
  const plannerProgress = useIncidentStreamStore((s) => s.plannerProgress);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(planMd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // 思考中：显示流式 Markdown
  if (!planMd && thinkingContent) {
    return (
      <div
        className={cn(
          "rounded-lg border border-blue-200 bg-blue-50/50 p-4 text-sm dark:border-blue-800 dark:bg-blue-950/50",
          "border-l-2 border-l-blue-400",
        )}
      >
        <div className="mb-1 text-xs font-medium text-muted-foreground">
          调查计划...
        </div>
        <Markdown content={thinkingContent} streaming variant="compact" components={PLAN_COMPONENTS} />
      </div>
    );
  }

  // 等待中
  if (!planMd && !thinkingContent) {
    if (planningStatus === "active") {
      const progressText =
        plannerProgress === "first_token_received"
          ? "已连接，正在生成调查计划"
          : plannerProgress === "llm_call_started"
            ? "正在制定计划"
            : "正在分析问题，生成调查计划";
      return (
        <div className="py-2">
          <TextDotsLoader text={progressText} size="sm" />
        </div>
      );
    }
    return null;
  }

  // 计划已生成：渲染蓝色卡片
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 text-sm dark:border-blue-800 dark:bg-blue-950/50">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-xs font-medium text-muted-foreground">调查计划</div>
        <button
          onClick={handleCopy}
          className="rounded p-0.5 text-muted-foreground hover:text-foreground"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        </button>
      </div>
      <Markdown content={planMd} variant="compact" components={PLAN_COMPONENTS} />
    </div>
  );
}
