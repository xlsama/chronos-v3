import { useState, useRef, useEffect } from "react";
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
      <span className="absolute left-0 top-2 z-10 flex h-3.5 w-3.5 -translate-x-1/2 items-center justify-center rounded-full bg-emerald-500">
        <Check className="h-2 w-2 text-white" strokeWidth={3} />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="absolute left-0 top-2 z-10 flex h-3.5 w-3.5 -translate-x-1/2 items-center justify-center">
        <motion.span
          className="absolute h-3.5 w-3.5 rounded-full bg-blue-400/15"
          animate={{ scale: [1, 1.8], opacity: [0.6, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
        />
        <span className="relative h-2 w-2 rounded-full bg-blue-400" />
      </span>
    );
  }
  return (
    <span className="absolute left-0 top-2.5 z-10 flex h-2.5 w-2.5 -translate-x-1/2 items-center justify-center">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/25" />
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
  const derivedExpanded = defaultExpanded ?? status === "active";
  const [userToggled, setUserToggled] = useState<boolean | null>(null);
  const expanded = userToggled ?? derivedExpanded;

  const prevStatusRef = useRef<PhaseStatus | null>(null);

  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = status;
    if (prev === null || prev === status) return;

    if (status === "active") {
      setUserToggled(null);
    } else if (prev === "active" && status === "completed" && !isLast) {
      // Delay collapse so the next phase expands first, avoiding a jarring jump
      const timer = setTimeout(() => setUserToggled(false), 300);
      return () => clearTimeout(timer);
    }
  }, [status, isLast]);

  return (
    <div className={cn("relative pl-6", !isLast && "pb-4")} data-testid="phase-section">
      {/* Timeline vertical line */}
      <div
        className={cn(
          "absolute left-0 -translate-x-1/2",
          "w-px bg-border/60",
          isLast ? "top-0 h-4" : "top-0 bottom-0",
        )}
        style={isLast ? { maskImage: "linear-gradient(to bottom, black, transparent)" } : undefined}
      />

      {/* Timeline node indicator */}
      <TimelineNodeIndicator status={status} />

      {/* Header */}
      <button
        className="flex w-full items-center gap-2 py-1.5 text-left"
        onClick={() => setUserToggled(!expanded)}
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
            transition={{ duration: 0.25, ease: "easeOut" }}
            style={{ overflow: "hidden" }}
          >
            <div className={cn("pt-1 pb-3", contentClassName)}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
