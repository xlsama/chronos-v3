import { createFileRoute } from "@tanstack/react-router";
import { ConnectionList } from "@/components/connections/connection-list";
import { CreateConnectionDialog } from "@/components/connections/create-connection-dialog";

export const Route = createFileRoute("/connections/")({
  component: ConnectionsPage,
});

function ConnectionsPage() {
  return (
    <div className="h-full">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">连接</h1>
        <CreateConnectionDialog />
      </div>
      <ConnectionList />
    </div>
  );
}
