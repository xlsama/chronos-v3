import { useState, useEffect, useRef } from "react";
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
}

function StatusIndicator({ status }: { status: PhaseStatus }) {
  if (status === "completed") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
        <Check className="h-3 w-3" />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="relative flex h-3 w-3">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
        <span className="relative inline-flex h-3 w-3 rounded-full bg-blue-500" />
      </span>
    );
  }
  return <span className="h-3 w-3 rounded-full bg-muted-foreground/30" />;
}

export function PhaseSection({
  title,
  subtitle,
  status,
  icon: Icon,
  children,
  defaultExpanded,
  contentClassName,
}: PhaseSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? status === "active");
  const [justCompleted, setJustCompleted] = useState(false);
  const prevStatusRef = useRef(status);

  // Auto-collapse when completed, auto-expand when active
  useEffect(() => {
    if (status === "active") setExpanded(true);
    if (status === "completed" && !defaultExpanded) setExpanded(false);
  }, [status, defaultExpanded]);

  // Flash green ring when transitioning active → completed
  useEffect(() => {
    if (prevStatusRef.current === "active" && status === "completed") {
      setJustCompleted(true);
      const timer = setTimeout(() => setJustCompleted(false), 800);
      return () => clearTimeout(timer);
    }
    prevStatusRef.current = status;
  }, [status]);

  return (
    <div className={cn(
      "rounded-lg border bg-card transition-shadow duration-500",
      justCompleted && "ring-2 ring-emerald-400/50",
    )} data-testid="phase-section">
      <button
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-[13px] font-medium">{title}</span>
        {subtitle && (
          <span className="text-xs text-muted-foreground">&middot; {subtitle}</span>
        )}
        <span className="ml-auto">
          <StatusIndicator status={status} />
        </span>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: "hidden" }}
          >
            <div className={cn("border-t px-4 py-3", contentClassName)}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
