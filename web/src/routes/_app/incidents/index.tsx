import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { IncidentList, STATUS_OPTIONS, SEVERITY_OPTIONS, STATUS_LABELS, SEVERITY_LABELS } from "@/components/incidents/incident-list";
import { CreateIncidentTrigger } from "@/components/incidents/create-incident-dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { pageVariants, pageTransition } from "@/lib/motion";

export const Route = createFileRoute("/_app/incidents/")({
  component: IncidentsPage,
});

function IncidentsPage() {
  const [statusFilter, setStatusFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");

  return (
    <motion.div
      className="flex h-full flex-col"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">状态</span>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-28">
              <SelectValue>{STATUS_LABELS[statusFilter]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-sm text-muted-foreground">等级</span>
          <Select value={severityFilter} onValueChange={setSeverityFilter}>
            <SelectTrigger className="w-28">
              <SelectValue>{SEVERITY_LABELS[severityFilter]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {SEVERITY_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <CreateIncidentTrigger />
      </div>
      <div className="flex flex-1 flex-col min-h-0">
        <IncidentList statusFilter={statusFilter} severityFilter={severityFilter} />
      </div>
    </motion.div>
  );
}
