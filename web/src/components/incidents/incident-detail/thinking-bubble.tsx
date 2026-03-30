import { memo } from "react";
import { Markdown } from "@/components/ui/markdown";

interface ThinkingBubbleProps {
  content: string;
  isStreaming?: boolean;
}

export const ThinkingBubble = memo(function ThinkingBubble({ content, isStreaming }: ThinkingBubbleProps) {
  return (
    <div
      className="text-sm py-3 text-foreground/80"
      data-testid="thinking-bubble"
    >
      <Markdown content={content} streaming={isStreaming} variant="compact" />
    </div>
  );
});
