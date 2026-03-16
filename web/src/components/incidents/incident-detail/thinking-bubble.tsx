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
      <div className="mb-1 text-xs font-medium text-muted-foreground">
        Agent Thinking {isStreaming && "..."}
      </div>
      <Markdown content={content} streaming={isStreaming} />
    </div>
  );
}
