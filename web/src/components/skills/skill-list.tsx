import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { motion } from "motion/react";
import { toast } from "sonner";
import { EllipsisVertical, Sparkles, Trash2 } from "lucide-react";
import { listVariants, listItemVariants } from "@/lib/motion";
import dayjs from "@/lib/dayjs";
import { client, orpc } from "@/lib/orpc";
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
import { QueryContent } from "@/components/query-content";

type Skill = Awaited<ReturnType<typeof client.skill.list>>[number];

interface SkillItemProps {
  skill: Skill;
  onSelect: () => void;
}

function SkillItem({ skill, onSelect }: SkillItemProps) {
  const queryClient = useQueryClient();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => client.skill.remove({ slug: skill.slug }),
    onSuccess: () => {
      toast.success("技能已删除");
      setShowDeleteDialog(false);
      queryClient.invalidateQueries({ queryKey: orpc.skill.list.key() });
    },
  });

  return (
    <>
      <div className="border-b last:border-b-0">
        <div
          className="group flex cursor-pointer items-center gap-3 border-l-2 border-l-transparent p-4 transition-colors hover:bg-muted/50 hover:border-l-primary/60"
          onClick={onSelect}
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p>{skill.name}</p>
              {skill.draft && <Badge variant="secondary">草稿</Badge>}
            </div>
            <p className="text-sm text-muted-foreground truncate">
              {skill.description}
            </p>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">
            {dayjs(skill.updatedAt).fromNow()}
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant="ghost" size="icon-sm" className="opacity-0 group-hover:opacity-100 transition-opacity" />}
              onClick={(e) => e.stopPropagation()}
            >
                <EllipsisVertical className="h-4 w-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                variant="destructive"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowDeleteDialog(true);
                }}
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
            <AlertDialogTitle>确认删除技能</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{skill.name}</strong> 吗？该操作无法撤销。
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

    </>
  );
}

interface SkillListProps {
  filter?: "published" | "draft";
}

export function SkillList({ filter }: SkillListProps) {
  const navigate = useNavigate();
  const { data: skills, isLoading } = useQuery(orpc.skill.list.queryOptions({}));

  const filteredSkills = useMemo(() => {
    if (!skills) return undefined;
    if (!filter) return skills;
    return skills.filter((s) => (filter === "draft" ? s.draft : !s.draft));
  }, [skills, filter]);

  return (
    <QueryContent
      isLoading={isLoading}
      data={filteredSkills}
      isEmpty={(d) => !d.length}
      skeleton={
        <div className="divide-y">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 p-4">
              <Skeleton className="h-5 w-5 rounded" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-48" />
              </div>
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-8 w-8" />
            </div>
          ))}
        </div>
      }
      empty={
        <Empty className="pt-[20vh]">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Sparkles />
            </EmptyMedia>
            <EmptyTitle>暂无技能</EmptyTitle>
            <EmptyDescription>
              创建技能来定义标准化的排查流程，Agent 排查时可调用。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      }
    >
      {(skills) => (
        <motion.div variants={listVariants} initial="initial" animate="animate">
          {skills.map((skill) => (
            <motion.div key={skill.slug} variants={listItemVariants}>
              <SkillItem
                skill={skill}
                onSelect={() => navigate({ to: "/skills/$slug", params: { slug: skill.slug } })}
              />
            </motion.div>
          ))}
        </motion.div>
      )}
    </QueryContent>
  );
}
