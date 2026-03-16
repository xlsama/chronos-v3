import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, ChevronRight, Check, type LucideIcon } from "lucide-react";
import type { PhaseStatus } from "@/stores/incident-stream";

interface PhaseSectionProps {
  title: string;
  status: PhaseStatus;
  icon: LucideIcon;
  children: React.ReactNode;
  defaultExpanded?: boolean;
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
  status,
  icon: Icon,
  children,
  defaultExpanded,
}: PhaseSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? status === "active");

  // Auto-collapse when completed, auto-expand when active
  useEffect(() => {
    if (status === "active") setExpanded(true);
    if (status === "completed" && !defaultExpanded) setExpanded(false);
  }, [status, defaultExpanded]);

  return (
    <div className="rounded-lg border bg-card" data-testid="phase-section">
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
        <span className="text-sm font-medium">{title}</span>
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
            <div className="border-t px-4 py-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
