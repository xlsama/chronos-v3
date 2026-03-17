import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Pencil, X, Server, Search } from "lucide-react";
import { getServers } from "@/api/servers";
import { updateProject } from "@/api/projects";
import type { Project } from "@/lib/types";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";

interface LinkedServersEditorProps {
  project: Project;
}

export function LinkedServersEditor({ project }: LinkedServersEditorProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  const { data: serversData } = useQuery({
    queryKey: ["servers", "all"],
    queryFn: () => getServers({ page_size: 200 }),
  });

  const allServers = serversData?.items;

  const updateMutation = useMutation({
    mutationFn: (ids: string[]) =>
      updateProject(project.id, { linked_server_ids: ids }),
    onSuccess: () => {
      toast.success("关联服务器已更新");
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
      setEditing(false);
    },
  });

  const linkedServers = useMemo(() => {
    if (!allServers) return [];
    const idSet = new Set(project.linked_server_ids);
    return allServers.filter((s) => idSet.has(s.id));
  }, [allServers, project.linked_server_ids]);

  const filteredServers = useMemo(() => {
    if (!allServers) return [];
    if (!search) return allServers;
    const q = search.toLowerCase();
    return allServers.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.host.toLowerCase().includes(q) ||
        (s.description?.toLowerCase().includes(q) ?? false),
    );
  }, [allServers, search]);

  const startEditing = () => {
    setSelectedIds(new Set(project.linked_server_ids));
    setSearch("");
    setEditing(true);
  };

  const toggleServer = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSave = () => {
    setShowConfirm(true);
  };

  const handleConfirmSave = () => {
    setShowConfirm(false);
    updateMutation.mutate([...selectedIds]);
  };

  if (!editing) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <Server className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">关联服务器:</span>
        {linkedServers.length > 0 ? (
          linkedServers.map((s) => (
            <Badge key={s.id} variant="secondary" className="text-xs">
              {s.name}
            </Badge>
          ))
        ) : (
          <span className="text-sm text-muted-foreground">无</span>
        )}
        <Button variant="ghost" size="icon-sm" onClick={startEditing}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">编辑关联服务器</span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditing(false)}
              disabled={updateMutation.isPending}
            >
              取消
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={updateMutation.isPending}
            >
              {updateMutation.isPending ? "保存中..." : "保存"}
            </Button>
          </div>
        </div>

        {/* Selected chips */}
        {selectedIds.size > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {[...selectedIds].map((id) => {
              const server = allServers?.find((s) => s.id === id);
              return (
                <Badge
                  key={id}
                  variant="secondary"
                  className="gap-1 pr-1 text-xs"
                >
                  {server?.name ?? id.slice(0, 8)}
                  <button
                    type="button"
                    className="rounded-full p-0.5 hover:bg-muted"
                    onClick={() => toggleServer(id)}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              );
            })}
          </div>
        )}

        {/* Search and list */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索服务器..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 text-sm"
          />
        </div>
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {filteredServers.length === 0 ? (
            <p className="p-3 text-center text-sm text-muted-foreground">
              没有找到服务器
            </p>
          ) : (
            filteredServers.map((server) => {
              const isSelected = selectedIds.has(server.id);
              return (
                <FieldLabel key={server.id}>
                  <Field orientation="horizontal">
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => toggleServer(server.id)}
                    />
                    <FieldContent>
                      <span className="text-sm font-medium">
                        {server.name}
                      </span>
                      {server.description && (
                        <FieldDescription>
                          {server.description}
                        </FieldDescription>
                      )}
                    </FieldContent>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {server.host}
                    </span>
                  </Field>
                </FieldLabel>
              );
            })
          )}
        </div>
      </div>

      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认更新关联服务器</AlertDialogTitle>
            <AlertDialogDescription>
              关联服务器已更改，请记得同步更新 SERVICE.md 文档以保持服务架构信息的准确性。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmSave}>
              确认保存
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
