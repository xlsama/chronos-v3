import { useState } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { motion } from "motion/react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, EllipsisVertical, KeyRound, Pencil, Server, Trash2, Wifi, WifiOff } from "lucide-react";
import { listVariants, listItemVariants } from "@/lib/motion";
import {
  deleteServer,
  getServers,
  testServer,
} from "@/api/servers";
import { cn } from "@/lib/utils";
import type { Server as ServerType } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { QueryContent } from "@/components/query-content";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EditServerDialog } from "./create-server-dialog";

const statusConfig: Record<string, { color: string; icon: typeof Wifi }> = {
  online: { color: "text-green-500", icon: Wifi },
  offline: { color: "text-red-500", icon: WifiOff },
  unknown: { color: "text-gray-400", icon: WifiOff },
};

const statusLabel: Record<string, string> = {
  online: "在线",
  offline: "离线",
  unknown: "未知",
};

const statusBadgeColors: Record<string, string> = {
  online: "bg-green-100 text-green-800 border-transparent",
  offline: "bg-red-100 text-red-800 border-transparent",
  unknown: "bg-gray-100 text-gray-800 border-transparent",
};

export function ServerItem({ server }: { server: ServerType }) {
  const queryClient = useQueryClient();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);

  const testMutation = useMutation({
    mutationFn: testServer,
    onSuccess: (data) => {
      if (data.success) {
        toast.success("连接测试成功");
      } else {
        toast.error("连接测试失败", { description: data.message });
      }
      queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteServer,
    onSuccess: () => {
      toast.success("服务器已删除");
      setShowDeleteDialog(false);
      queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
  });

  const status = statusConfig[server.status] ?? statusConfig.unknown;
  const StatusIcon = status.icon;

  return (
    <>
      <div data-testid={`server-item-${server.id}`} className="border-b last:border-b-0">
        <div className="flex items-center gap-3 p-4">
          <span className="text-lg">🖥️</span>
          <StatusIcon className={cn("h-4 w-4", status.color)} />
          <div className="flex-1 space-y-0.5">
            <p className="font-medium">{server.name}</p>
            <p className="text-sm text-muted-foreground">
              {`${server.username}@${server.host}:${server.port}`}
              {server.auth_method === "private_key" && (
                <KeyRound className="ml-1 inline h-3 w-3 text-muted-foreground" />
              )}
            </p>
            {server.description && (
              <p className="text-xs text-muted-foreground">{server.description}</p>
            )}
          </div>
          <Badge variant="outline" className="text-xs">
            SSH
          </Badge>
          {server.has_bastion && (
            <Badge variant="outline" className="text-xs">
              通过跳板机
            </Badge>
          )}
          <Badge
            className={
              statusBadgeColors[server.status] ?? statusBadgeColors.unknown
            }
          >
            {statusLabel[server.status] ?? "未知"}
          </Badge>
          <Button
            data-testid={`server-test-${server.id}`}
            variant="outline"
            size="sm"
            onClick={() => testMutation.mutate(server.id)}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? "测试中..." : "测试"}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" />}>
                <EllipsisVertical className="h-4 w-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setShowEditDialog(true)}>
                <Pencil className="mr-2 h-4 w-4" />
                编辑
              </DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                onClick={() => setShowDeleteDialog(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除服务器</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{server.name}</strong> 吗？该操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deleteMutation.mutate(server.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <EditServerDialog
        server={server}
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
      />
    </>
  );
}

export function ServerList() {
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: ["servers", page],
    queryFn: () => getServers({ page, page_size: pageSize }),
    placeholderData: keepPreviousData,
  });

  const servers = data?.items;
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <QueryContent
      isLoading={isLoading}
      data={data}
      isEmpty={(d) => !d.items?.length}
      skeleton={
        <div className="divide-y">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 p-4">
              <Skeleton className="h-4 w-4 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-48" />
              </div>
              <Skeleton className="h-5 w-16 rounded-full" />
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-8 w-8" />
            </div>
          ))}
        </div>
      }
      empty={
        <Empty className="pt-[20vh]">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Server />
            </EmptyMedia>
            <EmptyTitle>暂无服务器</EmptyTitle>
          </EmptyHeader>
        </Empty>
      }
    >
      {() => (
        <div className={isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <motion.div variants={listVariants} initial="initial" animate="animate">
            {servers!.map((server) => (
              <motion.div key={server.id} variants={listItemVariants}>
                <ServerItem server={server} />
              </motion.div>
            ))}
          </motion.div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <span className="text-sm text-muted-foreground">
                共 {total} 台
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="px-2 text-sm">
                  {page} / {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </QueryContent>
  );
}
