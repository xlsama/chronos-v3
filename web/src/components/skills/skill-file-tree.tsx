import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  File,
  FileCode,
  FileText,
  FolderOpen,
  Plus,
  Trash2,
} from "lucide-react";
import { deleteSkillFile } from "@/api/skills";
import { Button } from "@/components/ui/button";
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
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface SkillFileTreeProps {
  slug: string;
  scriptFiles: string[];
  referenceFiles: string[];
  assetFiles: string[];
  selectedFile: string | null; // null = SKILL.md
  dirtyFiles?: Set<string | null>;
  onSelectFile: (file: string | null) => void;
}

export function SkillFileTree({
  slug,
  scriptFiles,
  referenceFiles,
  assetFiles,
  selectedFile,
  dirtyFiles,
  onSelectFile,
}: SkillFileTreeProps) {
  const queryClient = useQueryClient();
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState<string | null>(null);
  const [newFileName, setNewFileName] = useState("");
  const [newFileDir, setNewFileDir] = useState<
    "scripts" | "references" | "assets"
  >("scripts");

  const deleteMutation = useMutation({
    mutationFn: (path: string) => deleteSkillFile(slug, path),
    onSuccess: () => {
      toast.success("文件已删除");
      queryClient.invalidateQueries({ queryKey: ["skill", slug] });
      setShowDeleteDialog(null);
      // If we deleted the selected file, go back to SKILL.md
      if (showDeleteDialog === selectedFile) {
        onSelectFile(null);
      }
    },
  });

  const hasScripts = scriptFiles.length > 0;
  const hasReferences = referenceFiles.length > 0;
  const hasAssets = assetFiles.length > 0;

  return (
    <div className="flex flex-col gap-0.5 text-sm">
      {/* SKILL.md — always on top */}
      <button
        className={cn(
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted/50",
          selectedFile === null && "bg-muted font-medium",
        )}
        onClick={() => onSelectFile(null)}
      >
        <FileText className="h-4 w-4 shrink-0 text-blue-500" />
        SKILL.md
        {dirtyFiles?.has(null) && (
          <span className="text-xs text-muted-foreground">●</span>
        )}
      </button>

      {/* scripts/ */}
      {hasScripts && (
        <div className="mt-1">
          <div className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-muted-foreground min-w-0">
            <FolderOpen className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">scripts/</span>
          </div>
          {scriptFiles.map((f) => (
            <div key={`scripts/${f}`} className="group flex items-center min-w-0">
              <button
                className={cn(
                  "flex flex-1 items-center gap-2 rounded-md px-2 py-1 pl-6 text-left hover:bg-muted/50 min-w-0",
                  selectedFile === `scripts/${f}` && "bg-muted font-medium",
                )}
                onClick={() => onSelectFile(`scripts/${f}`)}
              >
                <FileCode className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                <span className="truncate">{f}</span>
                {dirtyFiles?.has(`scripts/${f}`) && (
                  <span className="text-xs text-muted-foreground">●</span>
                )}
              </button>
              <button
                className="mr-1 rounded p-0.5 opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                onClick={() => setShowDeleteDialog(`scripts/${f}`)}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* references/ */}
      {hasReferences && (
        <div className="mt-1">
          <div className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-muted-foreground min-w-0">
            <FolderOpen className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">references/</span>
          </div>
          {referenceFiles.map((f) => (
            <div key={`references/${f}`} className="group flex items-center min-w-0">
              <button
                className={cn(
                  "flex flex-1 items-center gap-2 rounded-md px-2 py-1 pl-6 text-left hover:bg-muted/50 min-w-0",
                  selectedFile === `references/${f}` && "bg-muted font-medium",
                )}
                onClick={() => onSelectFile(`references/${f}`)}
              >
                <File className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                <span className="truncate">{f}</span>
                {dirtyFiles?.has(`references/${f}`) && (
                  <span className="text-xs text-muted-foreground">●</span>
                )}
              </button>
              <button
                className="mr-1 rounded p-0.5 opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                onClick={() => setShowDeleteDialog(`references/${f}`)}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* assets/ */}
      {hasAssets && (
        <div className="mt-1">
          <div className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-muted-foreground min-w-0">
            <FolderOpen className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">assets/</span>
          </div>
          {assetFiles.map((f) => (
            <div key={`assets/${f}`} className="group flex items-center min-w-0">
              <button
                className={cn(
                  "flex flex-1 items-center gap-2 rounded-md px-2 py-1 pl-6 text-left hover:bg-muted/50 min-w-0",
                  selectedFile === `assets/${f}` && "bg-muted font-medium",
                )}
                onClick={() => onSelectFile(`assets/${f}`)}
              >
                <File className="h-3.5 w-3.5 shrink-0 text-purple-500" />
                <span className="truncate">{f}</span>
                {dirtyFiles?.has(`assets/${f}`) && (
                  <span className="text-xs text-muted-foreground">●</span>
                )}
              </button>
              <button
                className="mr-1 rounded p-0.5 opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                onClick={() => setShowDeleteDialog(`assets/${f}`)}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add file button */}
      <button
        className="mt-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-muted-foreground hover:bg-muted/50 hover:text-foreground"
        onClick={() => {
          setNewFileName("");
          setNewFileDir("scripts");
          setShowAddDialog(true);
        }}
      >
        <Plus className="h-4 w-4" />
        添加文件
      </button>

      {/* Add file dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>添加文件</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Select
              value={newFileDir}
              onValueChange={(v) =>
                setNewFileDir(v as "scripts" | "references" | "assets")
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="scripts">scripts/</SelectItem>
                <SelectItem value="references">references/</SelectItem>
                <SelectItem value="assets">assets/</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder="文件名 (如 check.sh)"
              value={newFileName}
              onChange={(e) => setNewFileName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
            <Button
              disabled={!newFileName.trim()}
              onClick={() => {
                const path = `${newFileDir}/${newFileName.trim()}`;
                onSelectFile(path);
                setShowAddDialog(false);
              }}
            >
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog
        open={!!showDeleteDialog}
        onOpenChange={(open) => !open && setShowDeleteDialog(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{showDeleteDialog}</strong> 吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() =>
                showDeleteDialog && deleteMutation.mutate(showDeleteDialog)
              }
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
