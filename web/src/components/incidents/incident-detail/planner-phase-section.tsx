import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { Markdown } from "@/components/ui/markdown";
import { TextDotsLoader } from "@/components/ui/loader";

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
          "rounded-lg border border-blue-200 bg-blue-50/50 p-4 text-sm",
          "border-l-2 border-l-blue-400",
        )}
      >
        <div className="mb-1 text-xs font-medium text-muted-foreground">
          调查计划...
        </div>
        <Markdown content={thinkingContent} streaming variant="compact" />
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
    <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 text-sm">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-xs font-medium text-muted-foreground">调查计划</div>
        <button
          onClick={handleCopy}
          className="rounded p-0.5 text-muted-foreground hover:text-foreground"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        </button>
      </div>
      <Markdown content={planMd} variant="compact" />
    </div>
  );
}
