import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { EllipsisVertical, Sparkles, Trash2 } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { deleteSkill, getSkills } from "@/api/skills";
import type { Skill } from "@/lib/types";
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

interface SkillItemProps {
  skill: Skill;
  onSelect: () => void;
}

function SkillItem({ skill, onSelect }: SkillItemProps) {
  const queryClient = useQueryClient();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => deleteSkill(skill.slug),
    onSuccess: () => {
      toast.success("技能已删除");
      setShowDeleteDialog(false);
      queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });

  return (
    <>
      <div className="border-b last:border-b-0">
        <div
          className="group flex cursor-pointer items-center gap-3 p-4 hover:bg-muted/50"
          onClick={onSelect}
        >
          <Sparkles className="h-5 w-5 shrink-0 text-indigo-500" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-medium">{skill.name}</p>
              {skill.draft && <Badge variant="secondary">草稿</Badge>}
            </div>
            <p className="text-sm text-muted-foreground truncate">
              {skill.description}
            </p>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">
            {dayjs(skill.updated_at).fromNow()}
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

export function SkillList() {
  const navigate = useNavigate();
  const { data: skills, isLoading } = useQuery({
    queryKey: ["skills"],
    queryFn: getSkills,
  });

  if (isLoading) {
    return (
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
    );
  }

  if (!skills?.length) {
    return (
      <Empty className="pb-[20%]">
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
    );
  }

  return (
    <div>
      {skills.map((skill) => (
        <SkillItem
          key={skill.slug}
          skill={skill}
          onSelect={() => navigate({ to: "/skills/$slug", params: { slug: skill.slug } })}
        />
      ))}
    </div>
  );
}
