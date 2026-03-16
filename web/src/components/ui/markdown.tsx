import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";

interface MarkdownProps {
  content: string;
  streaming?: boolean;
  className?: string;
}

export function Markdown({ content, streaming, className }: MarkdownProps) {
  return (
    <Streamdown
      className={cn("prose prose-sm max-w-none dark:prose-invert", className)}
      mode={streaming ? "streaming" : "static"}
    >
      {content}
    </Streamdown>
  );
}
