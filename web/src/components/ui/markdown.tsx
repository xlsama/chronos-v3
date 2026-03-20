import { Streamdown } from "streamdown";
import type { AnimateOptions } from "streamdown";
import { code } from "@streamdown/code";
import { mermaid } from "@streamdown/mermaid";
import { cn } from "@/lib/utils";

const DEFAULT_ANIMATION: AnimateOptions = {
  animation: "blurIn",
  duration: 200,
  easing: "ease-out",
  sep: "word",
};

interface MarkdownProps {
  content: string;
  streaming?: boolean;
  className?: string;
  variant?: "default" | "compact" | "tiny";
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
        variant === "compact" ? "prose-compact" : variant === "tiny" ? "prose-tiny" : "prose-default",
        className,
      )}
      mode={streaming ? "streaming" : "static"}
      animated={DEFAULT_ANIMATION}
      isAnimating={!!streaming}
      caret={streaming ? "block" : undefined}
      plugins={{ code, mermaid }}
      shikiTheme={["github-light", "github-dark"]}
      controls={{ code: { copy: true, download: false } }}
    >
      {content}
    </Streamdown>
  );
}
