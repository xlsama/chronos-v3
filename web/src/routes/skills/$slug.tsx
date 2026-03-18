import { useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Pencil, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { deleteSkill, getSkill, updateSkill } from "@/api/skills";
import { parseFrontmatter } from "@/lib/frontmatter";
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
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/skills/$slug")({
  component: SkillDetailPage,
});

function SkillDetailPage() {
  const { slug } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const { data: skill, isLoading } = useQuery({
    queryKey: ["skill", slug],
    queryFn: () => getSkill(slug),
  });

  const parsed = skill ? parseFrontmatter(skill.content) : null;
  const draftParsed = draft !== null ? parseFrontmatter(draft) : null;

  function startEditing() {
    if (skill) {
      setDraft(skill.content);
      setEditing(true);
    }
  }

  function cancelEditing() {
    setEditing(false);
    setDraft(null);
  }

  const saveMutation = useMutation({
    mutationFn: () => updateSkill(slug, { content: draft! }),
    onSuccess: () => {
      toast.success("技能已保存");
      setEditing(false);
      setDraft(null);
      queryClient.invalidateQueries({ queryKey: ["skill", slug] });
      queryClient.invalidateQueries({ queryKey: ["skills"] });
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

  const displayName = (editing ? draftParsed?.name : parsed?.name) || slug;
  const displayDesc = editing ? draftParsed?.description : parsed?.description;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/skills">
            <Button variant="ghost" size="icon-sm">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div className="min-w-0">
            <h1 className="text-base font-medium truncate">{displayName}</h1>
            {displayDesc && (
              <p className="text-sm text-muted-foreground truncate">
                {displayDesc}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <Button size="sm" variant="outline" onClick={cancelEditing}>
                取消
              </Button>
              <Button
                size="sm"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || draft === null}
              >
                {saveMutation.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="mr-1.5 h-3.5 w-3.5" />
                )}
                保存
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" onClick={startEditing}>
              <Pencil className="mr-1.5 h-3.5 w-3.5" />
              编辑
            </Button>
          )}
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
      <div className="min-h-0 flex-1 p-4">
        {isLoading ? (
          <div className="space-y-3 p-4">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        ) : editing && draft !== null ? (
          <MarkdownEditor
            value={draft}
            onChange={setDraft}
            className="h-full"
            autoFocus
            previewTransform={(v) => parseFrontmatter(v).body}
            variant="default"
          />
        ) : parsed ? (
          <ScrollArea className="h-full">
            <div className="p-4">
              <Markdown content={parsed.body} />
            </div>
          </ScrollArea>
        ) : null}
      </div>

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
    </div>
  );
}
