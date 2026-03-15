import { cn } from "@/lib/utils";

interface ThinkingBubbleProps {
  content: string;
  isStreaming?: boolean;
}

export function ThinkingBubble({ content, isStreaming }: ThinkingBubbleProps) {
  return (
    <div
      className={cn(
        "rounded-lg bg-muted p-4 text-sm whitespace-pre-wrap",
        isStreaming && "border-l-2 border-primary",
      )}
    >
      <div className="mb-1 text-xs font-medium text-muted-foreground">
        Agent Thinking {isStreaming && "..."}
      </div>
      <div className="prose prose-sm max-w-none dark:prose-invert">
        {content}
      </div>
    </div>
  );
}
