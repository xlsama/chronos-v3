import { useState } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { motion } from "motion/react";
import { toast } from "sonner";
import {
  ChevronLeft,
  ChevronRight,
  Database,
  EllipsisVertical,
  Pencil,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";
import { client, orpc } from "@/lib/orpc";
import { cn } from "@/lib/utils";
import { ServiceIcon } from "@/lib/service-icons";
import type { Service } from "@/lib/types";
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ServiceForm } from "./service-form";
import { listVariants, listItemVariants } from "@/lib/motion";

const statusBadgeColors: Record<string, string> = {
  online: "bg-emerald-50 text-emerald-700 border-transparent dark:bg-emerald-950/40 dark:text-emerald-400",
  offline: "bg-red-50 text-red-700 border-transparent dark:bg-red-950/40 dark:text-red-400",
  unknown: "bg-slate-50 text-slate-600 border-transparent dark:bg-slate-800/40 dark:text-slate-400",
};

const statusLabel: Record<string, string> = {
  online: "在线",
  offline: "离线",
  unknown: "未知",
};

const statusConfig: Record<string, { color: string; icon: typeof Wifi }> = {
  online: { color: "text-emerald-500", icon: Wifi },
  offline: { color: "text-red-400", icon: WifiOff },
  unknown: { color: "text-slate-400", icon: WifiOff },
};

const typeLabels: Record<string, string> = {
  mysql: "MySQL",
  postgresql: "PostgreSQL",
  redis: "Redis",
  prometheus: "Prometheus",
  mongodb: "MongoDB",
  elasticsearch: "Elasticsearch",
  doris: "Apache Doris",
  starrocks: "StarRocks",
  jenkins: "Jenkins",
  kettle: "Kettle (Carte)",
  hive: "Apache Hive",
  kubernetes: "Kubernetes",
  docker: "Docker",
};

export function ServiceItem({ service }: { service: Service }) {
  const queryClient = useQueryClient();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);

  const testMutation = useMutation({
    mutationFn: (id: string) => client.service.test({ id }),
    onSuccess: (data) => {
      if (data.success) {
        toast.success("服务连接测试成功", {
          description: data.message,
        });
      } else {
        toast.error("服务连接测试失败", { description: data.message });
      }
      queryClient.invalidateQueries({ queryKey: orpc.service.list.key() });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => client.service.remove({ id }),
    onSuccess: () => {
      toast.success("服务已删除");
      setShowDeleteDialog(false);
      queryClient.invalidateQueries({ queryKey: orpc.service.list.key() });
    },
  });

  const status = statusConfig[service.status] ?? statusConfig.unknown;
  const StatusIcon = status.icon;

  return (
    <>
      <div className="border-b last:border-b-0">
        <div className="flex items-center gap-3 p-4">
          <ServiceIcon serviceType={service.serviceType} className="h-5 w-5" />
          <StatusIcon className={cn("h-4 w-4", status.color)} />
          <div className="flex-1 space-y-0.5">
            <p className="font-medium">{service.name}</p>
            <p className="text-sm text-muted-foreground">
              {service.host}:{service.port}
            </p>
            {service.description && (
              <p className="text-xs text-muted-foreground">
                {service.description}
              </p>
            )}
          </div>
          <Badge variant="outline" className="text-xs">
            {typeLabels[service.serviceType] ?? service.serviceType}
          </Badge>
          <Badge
            className={
              statusBadgeColors[service.status] ?? statusBadgeColors.unknown
            }
          >
            {statusLabel[service.status] ?? "未知"}
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => testMutation.mutate(service.id)}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? "测试中..." : "测试连接"}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant="ghost" size="icon-sm" />}
            >
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
            <AlertDialogTitle>确认删除服务</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{service.name}</strong> 吗？该操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deleteMutation.mutate(service.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>编辑服务</DialogTitle>
          </DialogHeader>
          <ServiceForm
            mode="edit"
            service={service}
            onSuccess={() => setShowEditDialog(false)}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

export function ServiceList() {
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const { data, isLoading, isPlaceholderData } = useQuery(orpc.service.list.queryOptions({
    input: { page, pageSize },
    placeholderData: keepPreviousData,
  }));

  const services = data?.items;
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
              <Database />
            </EmptyMedia>
            <EmptyTitle>暂无服务</EmptyTitle>
          </EmptyHeader>
        </Empty>
      }
    >
      {() => (
        <div className={isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <motion.div variants={listVariants} initial="initial" animate="animate">
            {services!.map((service) => (
              <motion.div key={service.id} variants={listItemVariants}>
                <ServiceItem service={service} />
              </motion.div>
            ))}
          </motion.div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <span className="text-sm text-muted-foreground">共 {total} 个</span>
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
