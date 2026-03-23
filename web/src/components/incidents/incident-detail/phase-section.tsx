import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, ChevronRight, Check, type LucideIcon } from "lucide-react";
import type { PhaseStatus } from "@/stores/incident-stream";
import { cn } from "@/lib/utils";

interface PhaseSectionProps {
  title: string;
  subtitle?: string;
  status: PhaseStatus;
  icon: LucideIcon;
  children: React.ReactNode;
  defaultExpanded?: boolean;
  contentClassName?: string;
  isLast?: boolean;
}

function TimelineNodeIndicator({ status }: { status: PhaseStatus }) {
  if (status === "completed") {
    return (
      <span className="absolute left-0 top-[10px] z-10 flex h-5 w-5 -translate-x-1/2 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 ring-4 ring-background">
        <Check className="h-3 w-3" />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="absolute left-0 top-[10px] z-10 flex h-3.5 w-3.5 -translate-x-1/2 items-center justify-center">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
        <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-blue-500 ring-4 ring-background" />
      </span>
    );
  }
  return (
    <span className="absolute left-0 top-[11px] z-10 flex h-3 w-3 -translate-x-1/2 items-center justify-center">
      <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30 ring-4 ring-background" />
    </span>
  );
}

export function PhaseSection({
  title,
  subtitle,
  status,
  icon: Icon,
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
    <div className="relative pl-6" data-testid="phase-section">
      {/* Timeline vertical line */}
      <div
        className={cn(
          "absolute left-0 w-px -translate-x-1/2 bg-border",
          isLast ? "top-0 h-[18px]" : "top-0 bottom-0",
        )}
      />

      {/* Timeline node indicator */}
      <TimelineNodeIndicator status={status} />

      {/* Header */}
      <button
        className="flex w-full items-center gap-2 py-1.5 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <Icon className="h-4 w-4 text-muted-foreground" />
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
