import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { mermaid } from "@streamdown/mermaid";
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
      className={cn(
        "streamdown-markdown",
        variant === "compact" ? "prose-compact" : "prose-default",
        className,
      )}
      mode={streaming ? "streaming" : "static"}
      plugins={{ code, mermaid }}
      shikiTheme={["github-light", "github-dark"]}
      controls={{ code: { copy: true, download: false } }}
    >
      {content}
    </Streamdown>
  );
}
