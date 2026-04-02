import { cn } from "@/lib/utils";

interface TextDotsLoaderProps {
  text: string;
  size?: "sm" | "md" | "lg";
}

export function TextDotsLoader({ text, size = "md" }: TextDotsLoaderProps) {
  const sizeClasses = {
    sm: "text-sm",
    md: "text-base",
    lg: "text-lg",
  };

  return (
    <div className={cn("flex items-center gap-2", sizeClasses[size])}>
      <span>{text}</span>
      <div className="flex gap-1">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}
