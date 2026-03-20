import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ServerList } from "@/components/servers/server-list";
import { ServiceList } from "@/components/connections/service-list";
import { ConnectionList } from "@/components/connections/connection-list";
import { AddConnectionDialog } from "@/components/connections/add-connection-dialog";
import { Database, Server } from "lucide-react";
import { pageVariants, pageTransition } from "@/lib/motion";

export const Route = createFileRoute("/connections/")({
  component: ConnectionsPage,
});

function ConnectionsPage() {
  return (
    <motion.div
      className="flex h-full flex-col"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
      <Tabs defaultValue="all" className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <TabsList>
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="service">
              <Database className="size-3.5" />
              服务
            </TabsTrigger>
            <TabsTrigger value="server">
              <Server className="size-3.5" />
              服务器
            </TabsTrigger>
          </TabsList>
          <AddConnectionDialog />
        </div>
        <TabsContent value="all" className="mt-0 flex flex-1 flex-col">
          <ConnectionList />
        </TabsContent>
        <TabsContent value="service" className="mt-0 flex flex-1 flex-col">
          <ServiceList />
        </TabsContent>
        <TabsContent value="server" className="mt-0 flex flex-1 flex-col">
          <ServerList />
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
