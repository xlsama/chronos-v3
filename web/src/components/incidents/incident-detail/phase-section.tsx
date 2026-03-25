import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, ChevronRight, Check } from "lucide-react";
import type { PhaseStatus } from "@/stores/incident-stream";
import { cn } from "@/lib/utils";

interface PhaseSectionProps {
  title: string;
  subtitle?: string;
  status: PhaseStatus;
  children: React.ReactNode;
  defaultExpanded?: boolean;
  contentClassName?: string;
  isLast?: boolean;
}

function TimelineNodeIndicator({ status }: { status: PhaseStatus }) {
  if (status === "completed") {
    return (
      <span className="absolute left-0 top-2 z-10 flex h-4 w-4 -translate-x-1/2 items-center justify-center rounded-full bg-blue-500 text-white ring-2 ring-blue-500/20">
        <Check className="h-2.5 w-2.5" strokeWidth={3} />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="absolute left-0 top-2 z-10 flex h-4 w-4 -translate-x-1/2 items-center justify-center">
        <span className="absolute h-4 w-4 animate-pulse rounded-full bg-blue-500/20" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-500 shadow-[0_0_6px_rgba(59,130,246,0.5)]" />
      </span>
    );
  }
  return (
    <span className="absolute left-0 top-2.5 z-10 flex h-2.5 w-2.5 -translate-x-1/2 items-center justify-center">
      <span className="h-2 w-2 rounded-full bg-muted-foreground/25 ring-2 ring-background" />
    </span>
  );
}

export function PhaseSection({
  title,
  subtitle,
  status,
  children,
  defaultExpanded,
  contentClassName,
  isLast,
}: PhaseSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? status === "active");

  // Auto-collapse when completed, auto-expand when active
  useEffect(() => {
    if (status === "active") setExpanded(true);
    if (status === "completed" && !defaultExpanded) setExpanded(false);
  }, [status, defaultExpanded]);

  return (
    <div className={cn("relative pl-6", !isLast && "pb-4")} data-testid="phase-section">
      {/* Timeline vertical line */}
      <div
        className={cn(
          "absolute left-0 w-px -translate-x-1/2 bg-border",
          isLast ? "top-0 h-4" : "top-0 bottom-0",
        )}
        style={isLast ? { maskImage: "linear-gradient(to bottom, black, transparent)" } : undefined}
      />

      {/* Timeline node indicator */}
      <TimelineNodeIndicator status={status} />

      {/* Header */}
      <button
        className="flex w-full items-center gap-2 py-1.5 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-[13px] font-medium">{title}</span>
        {subtitle && (
          <span className="text-xs text-muted-foreground">&middot; {subtitle}</span>
        )}
        <span className="ml-auto">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </span>
      </button>

      {/* Collapsible content */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: "hidden" }}
          >
            <div className={cn("pt-1 pb-3", contentClassName)}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
