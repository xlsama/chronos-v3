import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { EllipsisVertical, KeyRound, Pencil, Server, Trash2, Wifi, WifiOff } from "lucide-react";
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
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
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

function ServerItem({ server }: { server: ServerType }) {
  const queryClient = useQueryClient();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);

  const testMutation = useMutation({
    mutationFn: testServer,
    onSuccess: () => {
      toast.success("连接测试完成");
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
          {server.has_bastion && (
            <Badge variant="outline" className="text-xs">
              via bastion
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
  const { data: servers, isLoading } = useQuery({
    queryKey: ["servers"],
    queryFn: getServers,
  });

  if (isLoading) {
    return (
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
    );
  }

  if (!servers?.length) {
    return (
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Server />
          </EmptyMedia>
          <EmptyTitle>暂无服务器</EmptyTitle>
          <EmptyDescription>添加一台服务器以开始使用。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div>
      {servers.map((server) => (
        <ServerItem key={server.id} server={server} />
      ))}
    </div>
  );
}
