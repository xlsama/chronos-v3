import { useIncidentStreamStore } from "@/stores/incident-stream";
import { Markdown } from "@/components/ui/markdown";
import { TextDotsLoader } from "@/components/ui/loader";

export function PlannerContent() {
  const planMd = useIncidentStreamStore((s) => s.plannerPlanMd);
  const thinkingContent = useIncidentStreamStore((s) => s.plannerThinkingContent);
  const planningStatus = useIncidentStreamStore((s) => s.phaseState.planning);

  // 思考中：显示流式 Markdown
  if (!planMd && thinkingContent) {
    return (
      <div className="text-sm py-3 text-foreground/80">
        <Markdown content={thinkingContent} streaming variant="compact" />
      </div>
    );
  }

  // 等待中
  if (!planMd && !thinkingContent) {
    if (planningStatus === "active") {
      return (
        <div className="py-2">
          <TextDotsLoader text="正在分析问题，生成调查计划" size="sm" />
        </div>
      );
    }
    return null;
  }

  // 计划已生成：渲染完整 Markdown
  return (
    <div className="text-sm py-1">
      <Markdown content={planMd} variant="compact" />
    </div>
  );
}
