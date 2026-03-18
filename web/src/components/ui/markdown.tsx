import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { cn } from "@/lib/utils";

interface MarkdownProps {
  content: string;
  streaming?: boolean;
  className?: string;
  variant?: "default" | "compact";
}

export function Markdown({
  content,
  streaming,
  className,
  variant = "default",
}: MarkdownProps) {
  return (
    <Streamdown
      className={cn(variant === "compact" ? "prose-compact" : "prose-default", className)}
      mode={streaming ? "streaming" : "static"}
      plugins={{ code }}
      shikiTheme={["github-light", "github-dark"]}
      controls={{ code: { copy: true, download: false } }}
    >
      {content}
    </Streamdown>
  );
}
