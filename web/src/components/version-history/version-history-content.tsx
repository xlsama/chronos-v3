import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { orpc } from "@/lib/orpc";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { VersionDiffViewer } from "./version-diff-viewer";

interface VersionHistoryContentProps {
  entityType: string;
  entityId: string;
}

export function VersionHistoryContent({
  entityType,
  entityId,
}: VersionHistoryContentProps) {
  const [selected, setSelected] = useState<string | null>(null);

  const { data: versions, isLoading } = useQuery(orpc.version.list.queryOptions({
    input: { entityType, entityId },
  }));

  // 当版本列表变化时，自动选中最新版本
  const latestId = versions?.[0]?.id ?? null;

  useEffect(() => {
    setSelected(latestId);
  }, [latestId]);

  // 根据选中版本自动推导前一个版本
  const selectedIndex = versions?.findIndex((v) => v.id === selected) ?? -1;
  const prevId =
    selectedIndex >= 0 && versions && selectedIndex < versions.length - 1
      ? versions[selectedIndex + 1].id
      : null;

  const { data: newVersion, isLoading: newLoading } = useQuery(orpc.version.get.queryOptions({
    input: { id: selected! },
    enabled: !!selected,
  }));

  const { data: oldVersion, isLoading: oldLoading } = useQuery(orpc.version.get.queryOptions({
    input: { id: prevId! },
    enabled: !!prevId,
  }));

  const contentLoading = oldLoading || newLoading;

  return (
    <div className="flex min-h-0 flex-1">
      {/* Left: version list */}
      <div className="w-64 shrink-0 border-r">
        <ScrollArea className="h-full">
          <div className="p-3">
            <h3 className="mb-2 text-xs font-medium text-muted-foreground">
              版本列表
            </h3>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : !versions?.length ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                暂无版本记录
              </p>
            ) : (
              <div className="space-y-1">
                {versions.map((v) => {
                  return (
                    <button
                      key={v.id}
                      onClick={() => setSelected(v.id)}
                      className={cn(
                        "flex w-full flex-col gap-0.5 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent",
                        v.id === selected && "bg-accent",
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          v{v.versionNumber}
                        </span>
                        {v.id === versions?.[0]?.id && (
                          <Badge className="h-4 px-1 text-[10px] bg-green-100 text-green-700 border-green-200">
                            当前版本
                          </Badge>
                        )}
                        <Badge
                          variant="outline"
                          className="ml-auto h-4 px-1 text-[10px]"
                        >
                          {{ init: "初始", seed: "内置", seed_update: "内置更新", manual: "手动", auto: "自动" }[v.changeSource] ?? v.changeSource}
                        </Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {dayjs(v.createdAt).format("YYYY-MM-DD HH:mm")}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Right: diff viewer */}
      <div className="min-w-0 flex-1">
        {contentLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : oldVersion && newVersion ? (
          <VersionDiffViewer
            oldValue={oldVersion.content}
            newValue={newVersion.content}
            oldTitle={`v${oldVersion.versionNumber}`}
            newTitle={`v${newVersion.versionNumber}`}
          />
        ) : newVersion && !oldVersion ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">
              这是初始版本，暂无历史对比
            </p>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">
              {versions?.length
                ? "请选择一个版本查看变更"
                : "暂无版本记录"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
