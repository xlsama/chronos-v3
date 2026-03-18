import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import { z } from "zod";
import { createSkill } from "@/api/skills";
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
import { Field, FieldError, FieldLabel } from "@/components/ui/field";

const slugRegex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const skillSchema = z.object({
  slug: z
    .string()
    .min(1, "Slug 不能为空")
    .regex(slugRegex, "仅支持小写英文、数字和连字符"),
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
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (slug: string) => void;
}

export function SkillDialog({ open, onOpenChange, onCreated }: SkillDialogProps) {
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: createSkill,
    onSuccess: (_data, variables) => {
      toast.success("技能已创建");
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      onOpenChange(false);
      onCreated?.(variables.slug);
    },
  });

  const form = useForm({
    defaultValues: { slug: "" },
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
      createMutation.mutate({ slug: value.slug });
    },
  });

  const canSubmit = useStore(form.store, (s) => s.canSubmit);
  const isPending = createMutation.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (v) form.reset({ slug: "" });
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>创建技能</DialogTitle>
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
                <FieldLabel>Skill 目录名</FieldLabel>
                <Input
                  placeholder="例如: mysql-oom"
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
              {isPending ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
