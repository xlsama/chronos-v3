import { cn } from "@/lib/utils";

interface ShellCodeBlockProps {
  code: string;
  showPrompt?: boolean;
  className?: string;
}

export function ShellCodeBlock({
  code,
  showPrompt = true,
  className,
}: ShellCodeBlockProps) {
  return (
    <pre className={cn("m-0 bg-transparent p-0", className)}>
      {showPrompt && (
        <span className="select-none text-muted-foreground">$ </span>
      )}
      {code}
    </pre>
  );
}
