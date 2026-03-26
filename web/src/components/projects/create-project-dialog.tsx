import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "@tanstack/react-form";
import { createProject } from "@/api/projects";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";

export function CreateProjectDialog() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: createProject,
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      navigate({
        to: "/projects/$projectId",
        params: { projectId: project.id },
      });
    },
  });

  const form = useForm({
    defaultValues: { name: "", description: "" },
    onSubmit: ({ value }) => {
      mutation.mutate({
        name: value.name,
        description: value.description || undefined,
      });
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(open) => {
        setOpen(open);
        if (!open) form.reset();
      }}
    >
      <DialogTrigger render={<Button size="sm" />}>新建项目</DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>创建项目</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            form.handleSubmit();
          }}
        >
          <div className="space-y-4">
            <form.Field
              name="name"
              validators={{
                onSubmit: ({ value }) =>
                  !value ? "名称不能为空" : undefined,
              }}
            >
              {(field) => (
                <Field
                  data-invalid={
                    field.state.meta.errors.length > 0 || undefined
                  }
                >
                  <FieldLabel>名称</FieldLabel>
                  <Input
                    placeholder="项目名称"
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    onBlur={field.handleBlur}
                  />
                  <FieldError
                    errors={field.state.meta.errors.map((e) => ({
                      message: String(e),
                    }))}
                  />
                </Field>
              )}
            </form.Field>
            <form.Field name="description">
              {(field) => (
                <Field>
                  <FieldLabel>描述</FieldLabel>
                  <Textarea
                    placeholder="描述（选填）"
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    rows={3}
                  />
                </Field>
              )}
            </form.Field>
          </div>
          <DialogFooter className="mt-4">
            <DialogClose render={<Button variant="outline" />}>
              取消
            </DialogClose>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
