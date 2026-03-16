import { createFileRoute } from "@tanstack/react-router";
import { IncidentList } from "@/components/incidents/incident-list";
import { CreateIncidentDialog } from "@/components/incidents/create-incident-dialog";

export const Route = createFileRoute("/incidents/")({
  component: IncidentsPage,
});

function IncidentsPage() {
  return (
    <div className="h-full">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">事件</h1>
        <CreateIncidentDialog />
      </div>
      <IncidentList />
    </div>
  );
}
