import { CheckCircle } from "lucide-react";
import { Markdown } from "@/components/ui/markdown";

interface SummarySectionProps {
  markdown: string;
}

export function SummarySection({ markdown }: SummarySectionProps) {
  return (
    <div
      className="rounded-lg border border-green-200 bg-green-50/30 p-4"
      data-testid="summary-section"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-green-800">
        <CheckCircle className="h-5 w-5" />
        排查完成
      </div>
      <Markdown content={markdown} variant="compact" className="mt-3" />
    </div>
  );
}
