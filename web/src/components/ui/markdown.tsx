import { memo } from "react";
import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { createMermaidPlugin } from "@streamdown/mermaid";
import { cn } from "@/lib/utils";

const mermaid = createMermaidPlugin({
  config: {
    theme: "base",
    themeVariables: {
      fontSize: "12px",
    },
    flowchart: {
      useMaxWidth: false,
      nodeSpacing: 30,
      rankSpacing: 40,
      diagramPadding: 8,
      padding: 8,
    },
  },
});

interface MarkdownProps {
  content: string;
  streaming?: boolean;
  className?: string;
  variant?: "default" | "compact" | "tiny";
  allowedTags?: Record<string, string[]>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  components?: Record<string, React.ComponentType<any>>;
}

export const Markdown = memo(function Markdown({
  content,
  streaming,
  className,
  variant = "default",
  allowedTags,
  components,
}: MarkdownProps) {
  return (
    <Streamdown
      className={cn(
        "streamdown-markdown",
        variant === "compact" ? "prose-compact" : variant === "tiny" ? "prose-tiny" : "prose-default",
        className,
      )}
      mode={streaming ? "streaming" : "static"}
      isAnimating={!!streaming}
      caret={streaming ? "block" : undefined}
      plugins={{ code, mermaid }}
      shikiTheme={["github-light", "github-dark"]}
      controls={{ code: { copy: true, download: false } }}
      allowedTags={allowedTags}
      components={components}
    >
      {content}
    </Streamdown>
  );
});
