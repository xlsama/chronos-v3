import { createFileRoute } from "@tanstack/react-router";
import { InfrastructureList } from "@/components/infrastructure/infrastructure-list";
import { CreateInfrastructureDialog } from "@/components/infrastructure/create-infrastructure-dialog";

export const Route = createFileRoute("/infrastructure/")({
  component: InfrastructurePage,
});

function InfrastructurePage() {
  return (
    <div className="h-full">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-xl font-semibold">基础设施</h1>
        <CreateInfrastructureDialog />
      </div>
      <InfrastructureList />
    </div>
  );
}
