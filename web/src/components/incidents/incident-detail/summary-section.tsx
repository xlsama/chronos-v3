import { CheckCircle } from "lucide-react";

interface SummarySectionProps {
  markdown: string;
}

export function SummarySection({ markdown }: SummarySectionProps) {
  return (
    <div className="rounded-lg border-2 border-green-300 bg-green-50/50 p-4" data-testid="summary-section">
      <div className="flex items-center gap-2 text-sm font-semibold text-green-800">
        <CheckCircle className="h-5 w-5" />
        Investigation Complete
      </div>
      <div className="prose prose-sm mt-3 max-w-none dark:prose-invert whitespace-pre-wrap">
        {markdown}
      </div>
    </div>
  );
}
