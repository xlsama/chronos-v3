import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import { createConnection } from "@/api/connections";
import { connectionSchema } from "@/lib/schemas";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function fieldError(errors: unknown[]) {
  return errors.map((e) => ({
    message:
      typeof e === "string"
        ? e
        : (e as { message?: string })?.message ?? String(e),
  }));
}

export function CreateConnectionDialog({ projectId }: { projectId?: string }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createConnection,
    onSuccess: () => {
      toast.success("Connection added");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
      if (projectId) {
        queryClient.invalidateQueries({ queryKey: ["project-topology", projectId] });
      }
      setOpen(false);
    },
  });

  const form = useForm({
    defaultValues: {
      type: "ssh" as "ssh" | "kubernetes",
      name: "",
      description: "",
      host: "",
      port: "22",
      username: "root",
      password: "",
      kubeconfig: "",
      context: "",
      namespace: "",
    },
    onSubmit: ({ value }) => {
      const payload =
        value.type === "ssh"
          ? {
              type: "ssh" as const,
              name: value.name,
              description: value.description || undefined,
              host: value.host,
              port: parseInt(value.port),
              username: value.username,
              password: value.password || undefined,
              project_id: projectId,
            }
          : {
              type: "kubernetes" as const,
              name: value.name,
              description: value.description || undefined,
              kubeconfig: value.kubeconfig,
              context: value.context || undefined,
              namespace: value.namespace || undefined,
              project_id: projectId,
            };

      const result = connectionSchema.safeParse(payload);
      if (!result.success) {
        for (const issue of result.error.issues) {
          const path = issue.path?.[0]?.toString();
          if (path && path in form.state.values) {
            form.setFieldMeta(path as keyof typeof form.state.values, (prev) => ({
              ...prev,
              errorMap: { ...prev.errorMap, onSubmit: issue.message },
            }));
          }
        }
        return;
      }

      mutation.mutate(result.data);
    },
  });

  const type = useStore(form.store, (s) => s.values.type);

  return (
    <Dialog
      open={open}
      onOpenChange={(open) => {
        setOpen(open);
        if (!open) form.reset();
      }}
    >
      <DialogTrigger render={<Button size="sm" />}>
        Add Connection
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Connection</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            form.handleSubmit();
          }}
        >
          <div className="space-y-4">
            <form.Field name="type">
              {(field) => (
                <Field>
                  <FieldLabel>Type</FieldLabel>
                  <Select
                    value={field.state.value}
                    onValueChange={(v) =>
                      field.handleChange(v as "ssh" | "kubernetes")
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ssh">SSH Server</SelectItem>
                      <SelectItem value="kubernetes">
                        Kubernetes Cluster
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              )}
            </form.Field>

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
                  <FieldLabel>Name</FieldLabel>
                  <Input
                    placeholder={
                      type === "ssh"
                        ? "e.g. Production Server"
                        : "e.g. K8s Production"
                    }
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    onBlur={field.handleBlur}
                  />
                  <FieldError errors={fieldError(field.state.meta.errors)} />
                </Field>
              )}
            </form.Field>
            <form.Field name="description">
              {(field) => (
                <Field>
                  <FieldLabel>Description</FieldLabel>
                  <Textarea
                    placeholder="What this entry is used for"
                    rows={3}
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                  />
                </Field>
              )}
            </form.Field>

            {type === "ssh" ? (
              <>
                <div className="flex gap-3">
                  <form.Field
                    name="host"
                    validators={{
                      onSubmit: ({ value }) =>
                        !value ? "主机地址不能为空" : undefined,
                    }}
                  >
                    {(field) => (
                      <Field
                        className="flex-1"
                        data-invalid={
                          field.state.meta.errors.length > 0 || undefined
                        }
                      >
                        <FieldLabel>Host</FieldLabel>
                        <Input
                          placeholder="e.g. 192.168.1.1"
                          value={field.state.value}
                          onChange={(e) => field.handleChange(e.target.value)}
                          onBlur={field.handleBlur}
                        />
                        <FieldError
                          errors={fieldError(field.state.meta.errors)}
                        />
                      </Field>
                    )}
                  </form.Field>
                  <form.Field name="port">
                    {(field) => (
                      <Field className="w-24">
                        <FieldLabel>Port</FieldLabel>
                        <Input
                          type="number"
                          value={field.state.value}
                          onChange={(e) => field.handleChange(e.target.value)}
                        />
                      </Field>
                    )}
                  </form.Field>
                </div>
                <form.Field
                  name="username"
                  validators={{
                    onSubmit: ({ value }) =>
                      !value ? "用户名不能为空" : undefined,
                  }}
                >
                  {(field) => (
                    <Field
                      data-invalid={
                        field.state.meta.errors.length > 0 || undefined
                      }
                    >
                      <FieldLabel>Username</FieldLabel>
                      <Input
                        value={field.state.value}
                        onChange={(e) => field.handleChange(e.target.value)}
                        onBlur={field.handleBlur}
                      />
                      <FieldError
                        errors={fieldError(field.state.meta.errors)}
                      />
                    </Field>
                  )}
                </form.Field>
                <form.Field name="password">
                  {(field) => (
                    <Field>
                      <FieldLabel>Password</FieldLabel>
                      <Input
                        type="password"
                        placeholder="Optional"
                        value={field.state.value}
                        onChange={(e) => field.handleChange(e.target.value)}
                      />
                    </Field>
                  )}
                </form.Field>
              </>
            ) : (
              <>
                <form.Field
                  name="kubeconfig"
                  validators={{
                    onSubmit: ({ value }) =>
                      !value ? "Kubeconfig 不能为空" : undefined,
                  }}
                >
                  {(field) => (
                    <Field
                      data-invalid={
                        field.state.meta.errors.length > 0 || undefined
                      }
                    >
                      <FieldLabel>Kubeconfig</FieldLabel>
                      <Textarea
                        placeholder="Paste kubeconfig YAML content here..."
                        rows={6}
                        value={field.state.value}
                        onChange={(e) => field.handleChange(e.target.value)}
                        onBlur={field.handleBlur}
                      />
                      <FieldError
                        errors={fieldError(field.state.meta.errors)}
                      />
                    </Field>
                  )}
                </form.Field>
                <div className="flex gap-3">
                  <form.Field name="context">
                    {(field) => (
                      <Field className="flex-1">
                        <FieldLabel>Context</FieldLabel>
                        <Input
                          placeholder="Optional"
                          value={field.state.value}
                          onChange={(e) => field.handleChange(e.target.value)}
                        />
                      </Field>
                    )}
                  </form.Field>
                  <form.Field name="namespace">
                    {(field) => (
                      <Field className="flex-1">
                        <FieldLabel>Default Namespace</FieldLabel>
                        <Input
                          placeholder="default"
                          value={field.state.value}
                          onChange={(e) => field.handleChange(e.target.value)}
                        />
                      </Field>
                    )}
                  </form.Field>
                </div>
              </>
            )}
          </div>
          <DialogFooter className="mt-4">
            <DialogClose render={<Button variant="outline" />}>
              Cancel
            </DialogClose>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Adding..." : "Add"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
