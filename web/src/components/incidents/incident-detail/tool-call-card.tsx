import { cn } from "@/lib/utils";
import { Terminal } from "lucide-react";

interface ToolCallCardProps {
  name: string;
  args?: Record<string, unknown>;
  output?: string;
  isResult?: boolean;
}

export function ToolCallCard({
  name,
  args,
  output,
  isResult,
}: ToolCallCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        isResult ? "border-green-200 bg-green-50/50" : "border-blue-200 bg-blue-50/50",
      )}
      data-testid="tool-call-card"
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        <Terminal className="h-4 w-4" />
        <span data-testid="tool-name">{isResult ? "Result" : "Tool Call"}: {name}</span>
      </div>

      {args && (
        <pre className="mt-2 overflow-x-auto rounded bg-background p-2 text-xs">
          {JSON.stringify(args, null, 2)}
        </pre>
      )}

      {output && (
        <pre className="mt-2 max-h-60 overflow-auto rounded bg-background p-2 text-xs" data-testid="tool-output">
          {output}
        </pre>
      )}
    </div>
  );
}
