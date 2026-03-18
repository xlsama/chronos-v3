import { useState } from "react";
import { useDebounceFn } from "ahooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, Loader2, Search, Trash2 } from "lucide-react";
import dayjs from "@/lib/dayjs";
import {
  getIncidentHistoryList,
  deleteIncidentHistory,
} from "@/api/incident-history";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
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
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import type { IncidentHistory } from "@/lib/types";
import { IncidentHistoryDetailSheet } from "./incident-history-detail-sheet";

const PAGE_SIZE = 10;

export function IncidentHistoryPanel() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [detailItem, setDetailItem] = useState<IncidentHistory | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const { run: onSearchChange } = useDebounceFn(
    (val: string) => {
      setDebouncedSearch(val);
      setPage(1);
    },
    { wait: 300 },
  );

  const { data, isLoading } = useQuery({
    queryKey: ["incident-history", page, debouncedSearch],
    queryFn: () => getIncidentHistoryList(page, PAGE_SIZE, debouncedSearch || undefined),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteIncidentHistory,
    onSuccess: () => {
      setDeleteTarget(null);
      if (detailItem?.id === deleteTarget) setDetailItem(null);
      queryClient.invalidateQueries({ queryKey: ["incident-history"] });
    },
  });

  if (!isLoading && !data?.items.length && !debouncedSearch) {
    return (
      <Empty className="py-24">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <History />
          </EmptyMedia>
          <EmptyTitle>暂无历史事件</EmptyTitle>
          <EmptyDescription>
            事件归档以后会自动保存到这里。
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <>
      <div className="relative mb-3">
        <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="搜索历史事件..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            onSearchChange(e.target.value);
          }}
          className="h-8 pl-8 text-sm"
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 rounded-lg border p-4">
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-72" />
              </div>
              <Skeleton className="h-5 w-12 rounded-full" />
            </div>
          ))}
        </div>
      ) : !data?.items.length ? (
        <p className="py-8 text-center text-sm text-muted-foreground">未找到匹配的历史事件</p>
      ) : (
        <>
      <div className="space-y-2">
        {data.items.map((item) => (
          <button
            key={item.id}
            onClick={() => setDetailItem(item)}
            className="flex w-full items-center gap-3 rounded-lg border p-4 text-left transition-colors hover:bg-muted/50"
          >
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{item.title}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {dayjs(item.last_seen_at).fromNow()}
              </p>
            </div>
            {item.occurrence_count > 1 && (
              <Badge variant="secondary">
                {item.occurrence_count} 次
              </Badge>
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              className="shrink-0 text-muted-foreground hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(item.id);
              }}
            >
              <Trash2 className="size-4" />
            </Button>
          </button>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </Button>
        </div>
      )}
        </>
      )}

      <IncidentHistoryDetailSheet
        item={detailItem}
        onOpenChange={(open) => !open && setDetailItem(null)}
      />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              删除后该历史事件将无法恢复，确定要删除吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="animate-spin" />}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

