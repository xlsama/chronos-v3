import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import { z } from "zod";
import { createSkill, getSkill, updateSkill } from "@/api/skills";
import type { Skill } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";

const slugRegex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const skillSchema = z.object({
  slug: z
    .string()
    .min(1, "Slug 不能为空")
    .regex(slugRegex, "仅支持小写英文、数字和连字符"),
  name: z.string().min(1, "名称不能为空"),
  description: z.string().min(1, "描述不能为空"),
  content: z.string().min(1, "内容不能为空"),
});

function fieldError(errors: unknown[]) {
  return errors.map((e) => ({
    message:
      typeof e === "string"
        ? e
        : (e as { message?: string })?.message ?? String(e),
  }));
}

interface SkillDialogProps {
  skill?: Skill;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SkillDialog({ skill, open, onOpenChange }: SkillDialogProps) {
  const isEdit = !!skill;
  const queryClient = useQueryClient();

  // Fetch full detail (with content) when editing
  const { data: skillDetail } = useQuery({
    queryKey: ["skill", skill?.slug],
    queryFn: () => getSkill(skill!.slug),
    enabled: isEdit && open,
  });

  const createMutation = useMutation({
    mutationFn: createSkill,
    onSuccess: () => {
      toast.success("技能已创建");
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      onOpenChange(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: { name?: string; description?: string; content?: string }) =>
      updateSkill(skill!.slug, data),
    onSuccess: () => {
      toast.success("技能已更新");
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      queryClient.invalidateQueries({ queryKey: ["skill", skill!.slug] });
      onOpenChange(false);
    },
  });

  const form = useForm({
    defaultValues: {
      slug: "",
      name: "",
      description: "",
      content: "",
    },
    validators: {
      onSubmit: ({ value }) => {
        const result = skillSchema.safeParse(value);
        if (!result.success) {
          const fieldErrors: Record<string, string> = {};
          for (const issue of result.error.issues) {
            const path = issue.path.join(".");
            if (!fieldErrors[path]) fieldErrors[path] = issue.message;
          }
          return { fields: fieldErrors };
        }
        return undefined;
      },
    },
    onSubmit: ({ value }) => {
      if (isEdit) {
        updateMutation.mutate({
          name: value.name,
          description: value.description,
          content: value.content,
        });
      } else {
        createMutation.mutate(value);
      }
    },
  });

  // Reset form when dialog opens/skill changes
  useEffect(() => {
    if (open) {
      if (isEdit && skillDetail) {
        form.reset({
          slug: skill.slug,
          name: skillDetail.name,
          description: skillDetail.description,
          content: skillDetail.content,
        });
      } else if (!isEdit) {
        form.reset({
          slug: "",
          name: "",
          description: "",
          content: "",
        });
      }
    }
  }, [open, skillDetail]);

  const canSubmit = useStore(form.store, (s) => s.canSubmit);
  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑技能" : "创建技能"}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            form.handleSubmit();
          }}
          className="space-y-4"
        >
          <form.Field name="slug">
            {(field) => (
              <Field>
                <FieldLabel>Slug</FieldLabel>
                <Input
                  placeholder="例如: mysql-oom"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                  onBlur={field.handleBlur}
                  disabled={isEdit}
                />
                {field.state.meta.errors.length > 0 && (
                  <FieldError errors={fieldError(field.state.meta.errors)} />
                )}
              </Field>
            )}
          </form.Field>

          <form.Field name="name">
            {(field) => (
              <Field>
                <FieldLabel>名称</FieldLabel>
                <Input
                  placeholder="例如: MySQL OOM 排查"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                  onBlur={field.handleBlur}
                />
                {field.state.meta.errors.length > 0 && (
                  <FieldError errors={fieldError(field.state.meta.errors)} />
                )}
              </Field>
            )}
          </form.Field>

          <form.Field name="description">
            {(field) => (
              <Field>
                <FieldLabel>描述</FieldLabel>
                <Textarea
                  placeholder="简要描述这个技能的用途"
                  rows={2}
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                  onBlur={field.handleBlur}
                />
                {field.state.meta.errors.length > 0 && (
                  <FieldError errors={fieldError(field.state.meta.errors)} />
                )}
              </Field>
            )}
          </form.Field>

          <form.Field name="content">
            {(field) => (
              <Field>
                <FieldLabel>内容 (Markdown)</FieldLabel>
                <Textarea
                  placeholder="## 排查步骤&#10;1. 检查..."
                  rows={10}
                  className="font-mono text-sm"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                  onBlur={field.handleBlur}
                />
                {field.state.meta.errors.length > 0 && (
                  <FieldError errors={fieldError(field.state.meta.errors)} />
                )}
              </Field>
            )}
          </form.Field>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
                取消
            </DialogClose>
            <Button type="submit" disabled={!canSubmit || isPending}>
              {isPending
                ? isEdit
                  ? "保存中..."
                  : "创建中..."
                : isEdit
                  ? "保存"
                  : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

