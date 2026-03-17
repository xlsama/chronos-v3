import { cn } from "@/lib/utils";
import { Markdown } from "@/components/ui/markdown";

interface AnswerCardProps {
  content: string;
  isStreaming?: boolean;
}

export function AnswerCard({ content, isStreaming }: AnswerCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-violet-200 bg-violet-50/50 p-4 text-sm",
        isStreaming && "border-l-2 border-l-violet-400",
      )}
    >
      <div className="mb-1 text-xs font-medium text-muted-foreground">
        排查结论{isStreaming && "..."}
      </div>
      <Markdown content={content} streaming={isStreaming} variant="compact" />
    </div>
  );
}
