import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { IncidentList } from "@/components/incidents/incident-list";
import { CreateIncidentDialog } from "@/components/incidents/create-incident-dialog";
import { pageVariants, pageTransition } from "@/lib/motion";

export const Route = createFileRoute("/incidents/")({
  component: IncidentsPage,
});

function IncidentsPage() {
  return (
    <motion.div
      className="flex h-full flex-col"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">事件</h1>
        <CreateIncidentDialog />
      </div>
      <div className="flex flex-1 flex-col">
        <IncidentList />
      </div>
    </motion.div>
  );
}
