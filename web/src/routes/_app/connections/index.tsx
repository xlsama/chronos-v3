import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ServerList } from "@/components/servers/server-list";
import { ServiceList } from "@/components/connections/service-list";
import { ConnectionList } from "@/components/connections/connection-list";
import { AddConnectionDialog } from "@/components/connections/add-connection-dialog";
import { Database, Server, Zap } from "lucide-react";
import { pageVariants, pageTransition } from "@/lib/motion";
import { client, orpc } from "@/lib/orpc";

export const Route = createFileRoute("/_app/connections/")({
  component: ConnectionsPage,
});

function ConnectionsPage() {
  const queryClient = useQueryClient();

  const batchTestMutation = useMutation({
    mutationFn: () => client.connection.testAll({}),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: orpc.server.list.key() });
      queryClient.invalidateQueries({ queryKey: orpc.service.list.key() });

      if (data.total === 0) {
        toast.info("没有可测试的连接");
        return;
      }

      if (data.failureCount === 0) {
        toast.success(`全部 ${data.total} 个连接测试通过`);
      } else {
        const failedNames = data.results
          .filter((r) => !r.success)
          .map((r) => r.name)
          .join("、");
        toast.error(
          `${data.successCount} 个成功，${data.failureCount} 个失败`,
          { description: `失败: ${failedNames}` },
        );
      }
    },
  });

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
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => batchTestMutation.mutate()}
              disabled={batchTestMutation.isPending}
            >
              <Zap className="size-3.5" />
              {batchTestMutation.isPending ? "测试中..." : "测试所有连接"}
            </Button>
            <AddConnectionDialog />
          </div>
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
