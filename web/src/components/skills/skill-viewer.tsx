import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Loader2, Pencil, Save } from "lucide-react";
import { toast } from "sonner";
import { getSkill, updateSkill } from "@/api/skills";
import { parseFrontmatter } from "@/lib/frontmatter";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Markdown } from "@/components/ui/markdown";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { QueryContent } from "@/components/query-content";

interface SkillViewerProps {
  skillSlug: string | null;
  onClose: () => void;
  autoEdit?: boolean;
  readOnly?: boolean;
}

export function SkillViewer({ skillSlug, onClose, autoEdit, readOnly }: SkillViewerProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const autoEditApplied = useRef(false);

  const { data: skill, isLoading } = useQuery({
    queryKey: ["skill", skillSlug],
    queryFn: () => getSkill(skillSlug!),
    enabled: !!skillSlug,
  });

  const saveMutation = useMutation({
    mutationFn: () => updateSkill(skillSlug!, { content: draft }),
    onSuccess: () => {
      toast.success("技能已保存");
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["skill", skillSlug] });
      queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });

  function startEditing() {
    if (skill) {
      setDraft(skill.content);
      setEditing(true);
    }
  }

  useEffect(() => {
    if (autoEdit && skill && !editing && !autoEditApplied.current) {
      autoEditApplied.current = true;
      startEditing();
    }
  }, [autoEdit, skill]);

  useEffect(() => {
    setEditing(false);
    setDraft("");
    autoEditApplied.current = false;
  }, [skillSlug]);

  return (
    <Dialog open={!!skillSlug} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex h-[80vh] flex-col overflow-hidden sm:max-w-[80vw]">
        <DialogHeader className="flex-row items-center justify-between gap-2 space-y-0">
          <div className="min-w-0 space-y-1">
            <DialogTitle className="truncate">
              {(editing ? parseFrontmatter(draft).name : skill?.name) || "技能预览"}
            </DialogTitle>
            {(editing ? parseFrontmatter(draft).description : skill?.description) && (
              <DialogDescription className="truncate">
                {editing ? parseFrontmatter(draft).description : skill?.description}
              </DialogDescription>
            )}
          </div>
          <div className="mr-6 flex items-center gap-2">
            {!readOnly && !editing && (
              <Button variant="outline" size="sm" onClick={startEditing}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" />
                编辑
              </Button>
            )}
            {editing && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setEditing(false)}
                >
                  <Eye className="mr-1.5 h-3.5 w-3.5" />
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  保存
                </Button>
              </>
            )}
          </div>
        </DialogHeader>
        <div className="min-h-0 flex-1">
          <QueryContent
            className="h-full"
            isLoading={isLoading}
            data={skill}
            skeleton={
              <div className="space-y-3 p-4">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            }
            empty={<div />}
          >
            {(skill) =>
              editing ? (
                <MarkdownEditor
                  value={draft}
                  onChange={setDraft}
                  className="h-full"
                  autoFocus
                  previewTransform={(v) => parseFrontmatter(v).body}
                  variant="default"
                />
              ) : (
                <ScrollArea className="h-full" scrollToTop>
                  <div className="p-4">
                    <Markdown content={parseFrontmatter(skill.content).body} />
                  </div>
                </ScrollArea>
              )
            }
          </QueryContent>
        </div>
      </DialogContent>
    </Dialog>
  );
}
