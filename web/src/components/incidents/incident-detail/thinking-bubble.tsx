import { cn } from "@/lib/utils";
import { Markdown } from "@/components/ui/markdown";

interface ThinkingBubbleProps {
  content: string;
  isStreaming?: boolean;
}

export function ThinkingBubble({ content, isStreaming }: ThinkingBubbleProps) {
  return (
    <div
      className={cn(
        "rounded-lg bg-muted p-4 text-sm",
        isStreaming && "border-l-2 border-primary",
      )}
      data-testid="thinking-bubble"
    >
      <div className={cn(
        "mb-1 text-xs font-medium text-muted-foreground",
        isStreaming && "animate-pulse",
      )}>
        Agent 思考中{isStreaming && "..."}
      </div>
      <div className="relative">
        <Markdown content={content} streaming={isStreaming} variant="compact" />
        {isStreaming && (
          <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-primary/60" />
        )}
      </div>
    </div>
  );
}
