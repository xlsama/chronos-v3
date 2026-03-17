import { createFileRoute } from "@tanstack/react-router";
import { ServerList } from "@/components/servers/server-list";
import { CreateServerDialog } from "@/components/servers/create-server-dialog";

export const Route = createFileRoute("/servers/")({
  component: ServersPage,
});

function ServersPage() {
  return (
    <div className="h-full">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">服务器</h1>
        <CreateServerDialog />
      </div>
      <ServerList />
    </div>
  );
}
