import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";

interface MarkdownProps {
  content: string;
  streaming?: boolean;
  className?: string;
  variant?: "default" | "compact";
}

export function Markdown({ content, streaming, className, variant = "default" }: MarkdownProps) {
  return (
    <Streamdown
      className={cn(
        "prose prose-sm max-w-none dark:prose-invert",
        variant === "compact" && "prose-compact",
        className
      )}
      mode={streaming ? "streaming" : "static"}
    >
      {content}
    </Streamdown>
  );
}
