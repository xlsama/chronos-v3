import { useCallback, useEffect, useMemo, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { ArrowLeft, History, Loader2, Pencil, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { pageVariants, pageTransition } from "@/lib/motion";
import {
  deleteSkill,
  getSkill,
  getSkillFile,
  putSkillFile,
  updateSkill,
} from "@/api/skills";
import { parseFrontmatter } from "@/lib/frontmatter";
import { VersionHistoryDialog } from "@/components/version-history/version-history-dialog";
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
import { CodeEditor, getLanguageFromPath } from "@/components/ui/code-editor";
import { Markdown } from "@/components/ui/markdown";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { SkillFileTree } from "@/components/skills/skill-file-tree";
import { QueryContent } from "@/components/query-content";

export const Route = createFileRoute("/_app/skills/$slug")({
  component: SkillDetailPage,
});

function SkillDetailPage() {
  const { slug } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Skill-level editing state
  const [editing, setEditing] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  // key: null = SKILL.md, "scripts/xxx.sh" = attached file
  const [drafts, setDrafts] = useState<Map<string | null, string>>(new Map());
  const [originals, setOriginals] = useState<Map<string | null, string>>(new Map());

  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showDiscardDialog, setShowDiscardDialog] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const { data: skill, isLoading } = useQuery({
    queryKey: ["skill", slug],
    queryFn: () => getSkill(slug),
  });

  // Check if selected file exists on backend
  const isExistingFile =
    !!selectedFile &&
    (skill?.script_files?.some((f) => `scripts/${f}` === selectedFile) ||
      skill?.reference_files?.some(
        (f) => `references/${f}` === selectedFile,
      ) ||
      skill?.asset_files?.some(
        (f) => `assets/${f}` === selectedFile,
      ));

  // Fetch file content only for existing files
  const { data: fileData, isLoading: fileLoading } = useQuery({
    queryKey: ["skill-file", slug, selectedFile],
    queryFn: () => getSkillFile(slug, selectedFile!),
    enabled: !!selectedFile && isExistingFile,
  });

  // When file data loads and we're in edit mode, initialize draft if not yet set
  useEffect(() => {
    if (fileData && editing && selectedFile && !drafts.has(selectedFile)) {
      // oxlint-disable-next-line react/set-state-in-effect -- sync query data into local draft state
      setDrafts((prev) => new Map(prev).set(selectedFile, fileData.content));
      setOriginals((prev) => new Map(prev).set(selectedFile, fileData.content));
    }
  }, [fileData, editing, selectedFile, drafts]);

  // When selecting a new non-existing file in edit mode, initialize with empty
  useEffect(() => {
    if (selectedFile && !isExistingFile && editing && !drafts.has(selectedFile)) {
      // oxlint-disable-next-line react/set-state-in-effect -- init empty draft for new file
      setDrafts((prev) => new Map(prev).set(selectedFile, ""));
      setOriginals((prev) => new Map(prev).set(selectedFile, ""));
    }
  }, [selectedFile, isExistingFile, editing, drafts]);

  const parsed = skill ? parseFrontmatter(skill.content) : null;
  const draftContent = drafts.get(null);
  const draftParsed = draftContent !== undefined ? parseFrontmatter(draftContent) : null;

  const displayName =
    (editing && draftParsed ? draftParsed.name : parsed?.name) || slug;
  const displayDesc = editing && draftParsed
    ? draftParsed.description
    : parsed?.description;

  // Draft helpers
  const updateDraft = useCallback((key: string | null, content: string) => {
    setDrafts((prev) => new Map(prev).set(key, content));
  }, []);

  const isDirty = useCallback(
    (key: string | null) => {
      const d = drafts.get(key);
      const o = originals.get(key);
      return d !== undefined && d !== o;
    },
    [drafts, originals],
  );

  const currentDirty = isDirty(selectedFile);

  const anyDirty = useMemo(() => {
    for (const [key] of drafts) {
      if (isDirty(key)) return true;
    }
    return false;
  }, [drafts, isDirty]);

  // Dirty files set for file tree indicator
  const dirtyFiles = useMemo(() => {
    const s = new Set<string | null>();
    for (const [key] of drafts) {
      if (isDirty(key)) s.add(key);
    }
    return s;
  }, [drafts, isDirty]);

  // Start/stop editing
  function startEditing() {
    if (!skill) return;
    setEditing(true);
    setDrafts(new Map([[null, skill.content]]));
    setOriginals(new Map([[null, skill.content]]));
    // If currently viewing a file, also init its draft
    if (selectedFile && fileData) {
      setDrafts((prev) =>
        new Map(prev).set(selectedFile, fileData.content),
      );
      setOriginals((prev) =>
        new Map(prev).set(selectedFile, fileData.content),
      );
    }
  }

  function requestStopEditing() {
    if (anyDirty) {
      setShowDiscardDialog(true);
    } else {
      forceStopEditing();
    }
  }

  function forceStopEditing() {
    setEditing(false);
    setDrafts(new Map());
    setOriginals(new Map());
  }

  // Unified save
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (selectedFile === null) {
        const content = drafts.get(null);
        if (content === undefined) throw new Error("No draft");
        return updateSkill(slug, { content });
      } else {
        const content = drafts.get(selectedFile);
        if (content === undefined) throw new Error("No draft");
        return putSkillFile(slug, selectedFile, content);
      }
    },
    onSuccess: () => {
      const key = selectedFile;
      const content = drafts.get(key);
      toast.success(key === null ? "SKILL.md 已保存" : "文件已保存");
      // Update originals so dirty clears
      if (content !== undefined) {
        setOriginals((prev) => new Map(prev).set(key, content));
      }
      queryClient.invalidateQueries({ queryKey: ["skill", slug] });
      queryClient.invalidateQueries({ queryKey: ["versions", "skill", slug] });
      if (key !== null) {
        queryClient.invalidateQueries({
          queryKey: ["skill-file", slug, key],
        });
      } else {
        queryClient.invalidateQueries({ queryKey: ["skills"] });
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteSkill(slug),
    onSuccess: () => {
      toast.success("技能已删除");
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      navigate({ to: "/skills" });
    },
  });

  // Current file display content for view / edit
  const currentFileDraft = drafts.get(selectedFile);
  const currentFileContent = selectedFile
    ? fileData?.content ?? ""
    : "";

  return (
    <motion.div
      className="flex h-full flex-col"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/skills">
            <Button variant="ghost" size="icon-sm">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-medium truncate">{displayName}</h1>
              {skill?.draft && (
                <Badge variant="secondary" className="shrink-0">草稿</Badge>
              )}
            </div>
            {displayDesc && (
              <p className="text-sm text-muted-foreground truncate">
                {displayDesc}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <Button size="sm" variant="outline" onClick={requestStopEditing}>
              <Pencil className="mr-1.5 h-3.5 w-3.5" />
              完成编辑
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={startEditing}>
              <Pencil className="mr-1.5 h-3.5 w-3.5" />
              编辑
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setShowHistory(true)}>
            <History className="mr-1.5 h-3.5 w-3.5" />
            更新历史
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => setShowDeleteDialog(true)}
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            删除
          </Button>
        </div>
      </div>
      {/* Content */}
      <div className="min-h-0 flex-1">
        <QueryContent
          isLoading={isLoading}
          data={skill}
          className="h-full"
          skeleton={
            <div className="space-y-3 p-6">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          }
          empty={<div />}
        >
          {(skill) => (
            <div className="flex h-full">
              {/* Left: File Tree */}
              <aside className="w-60 shrink-0 border-r overflow-y-auto p-3">
                <SkillFileTree
                  slug={slug}
                  scriptFiles={skill.script_files}
                  referenceFiles={skill.reference_files}
                  assetFiles={skill.asset_files}
                  selectedFile={selectedFile}
                  dirtyFiles={editing ? dirtyFiles : undefined}
                  onSelectFile={(f) => {
                    setSelectedFile(f);
                  }}
                />
              </aside>

              {/* Right: Editor */}
              <div className="flex-1 min-w-0 flex flex-col">
                {/* Toolbar */}
                <div className="flex items-center justify-between border-b px-4 py-2">
                  <span className="text-sm text-muted-foreground">
                    {selectedFile ?? "SKILL.md"}
                  </span>
                  {editing && (
                    <Button
                      size="sm"
                      onClick={() => saveMutation.mutate()}
                      disabled={saveMutation.isPending || !currentDirty}
                    >
                      {saveMutation.isPending ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Save className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      保存
                    </Button>
                  )}
                </div>

                {/* Editor area */}
                <div className="min-h-0 flex-1">
                  {selectedFile === null ? (
                    // SKILL.md
                    (editing && currentFileDraft !== undefined ? (<div className="h-full p-4">
                      <MarkdownEditor
                        value={currentFileDraft}
                        onChange={(v) => updateDraft(null, v)}
                        className="h-full"
                        autoFocus
                        previewTransform={(v) => parseFrontmatter(v).body}
                        variant="default"
                      />
                    </div>) : parsed ? (
                      <ScrollArea className="h-full p-4" scrollToTop>
                        <Markdown content={parsed.body} />
                      </ScrollArea>
                    ) : null)
                  ) : (
                    // Attached file
                    (fileLoading ? (<div className="p-6 space-y-3">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-4 w-1/2" />
                    </div>) : editing ? (
                      <CodeEditor
                        value={currentFileDraft ?? currentFileContent}
                        onChange={(v) => updateDraft(selectedFile, v)}
                        language={getLanguageFromPath(selectedFile)}
                      />
                    ) : (
                      <CodeEditor
                        value={currentFileContent}
                        language={getLanguageFromPath(selectedFile)}
                        readOnly
                      />
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </QueryContent>
      </div>
      {/* Delete dialog */}
      <AlertDialog
        open={showDeleteDialog}
        onOpenChange={(open) => !open && setShowDeleteDialog(false)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除技能</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{parsed?.name || slug}</strong>{" "}
              吗？该操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* Discard unsaved changes dialog */}
      <AlertDialog
        open={showDiscardDialog}
        onOpenChange={(open) => !open && setShowDiscardDialog(false)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>未保存的修改</AlertDialogTitle>
            <AlertDialogDescription>
              有未保存的修改，确定要丢弃吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>继续编辑</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                setShowDiscardDialog(false);
                forceStopEditing();
              }}
            >
              丢弃修改
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <VersionHistoryDialog
        open={showHistory}
        onOpenChange={setShowHistory}
        entityType="skill"
        entityId={slug}
        title={`技能 ${displayName} 更新历史`}
      />
    </motion.div>
  )
}
