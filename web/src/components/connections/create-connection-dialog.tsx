import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { createConnection, updateConnection } from "@/api/connections";
import { connectionSchema } from "@/lib/schemas";
import type { Connection } from "@/lib/types";
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

type FormValues = {
  type: "ssh" | "kubernetes";
  name: string;
  description: string;
  host: string;
  port: string;
  username: string;
  auth_method: "password" | "private_key";
  password: string;
  private_key: string;
  kubeconfig: string;
  context: string;
  namespace: string;
};

function ConnectionForm({
  mode,
  connection,
  projectId,
  onSuccess,
}: {
  mode: "create" | "edit";
  connection?: Connection;
  projectId?: string;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = mode === "edit";

  const createMutation = useMutation({
    mutationFn: createConnection,
    onSuccess: () => {
      toast.success("Connection added");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
      if (projectId) {
        queryClient.invalidateQueries({ queryKey: ["project-topology", projectId] });
      }
      onSuccess();
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: Parameters<typeof updateConnection>[1]) =>
      updateConnection(connection!.id, data),
    onSuccess: () => {
      toast.success("Connection updated");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
      onSuccess();
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const defaultValues: FormValues = isEdit && connection
    ? {
        type: connection.type as "ssh" | "kubernetes",
        name: connection.name,
        description: connection.description ?? "",
        host: connection.host,
        port: String(connection.port),
        username: connection.username,
        auth_method: connection.auth_method === "private_key" ? "private_key" : "password",
        password: "",
        private_key: "",
        kubeconfig: "",
        context: "",
        namespace: "",
      }
    : {
        type: "ssh",
        name: "",
        description: "",
        host: "",
        port: "22",
        username: "root",
        auth_method: "password",
        password: "",
        private_key: "",
        kubeconfig: "",
        context: "",
        namespace: "",
      };

  const form = useForm({
    defaultValues,
    onSubmit: ({ value }) => {
      if (isEdit) {
        const data: Record<string, unknown> = {};
        if (value.name !== connection!.name) data.name = value.name;
        if ((value.description || "") !== (connection!.description || ""))
          data.description = value.description || undefined;

        if (connection!.type === "ssh") {
          if (value.host !== connection!.host) data.host = value.host;
          if (parseInt(value.port) !== connection!.port) data.port = parseInt(value.port);
          if (value.username !== connection!.username) data.username = value.username;
          if (value.auth_method === "password" && value.password) {
            data.password = value.password;
            data.private_key = null;
          } else if (value.auth_method === "private_key" && value.private_key) {
            data.private_key = value.private_key;
            data.password = null;
          }
        } else {
          if (value.kubeconfig) data.kubeconfig = value.kubeconfig;
          if (value.context) data.context = value.context;
          if (value.namespace) data.namespace = value.namespace;
        }

        if (Object.keys(data).length === 0) {
          onSuccess();
          return;
        }
        updateMutation.mutate(data as Parameters<typeof updateConnection>[1]);
        return;
      }

      // Create mode - use zod validation
      const payload =
        value.type === "ssh"
          ? {
              type: "ssh" as const,
              name: value.name,
              description: value.description || undefined,
              host: value.host,
              port: parseInt(value.port),
              username: value.username,
              auth_method: value.auth_method,
              ...(value.auth_method === "password"
                ? { password: value.password || undefined }
                : { private_key: value.private_key || undefined }),
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

      createMutation.mutate(result.data);
    },
  });

  const type = useStore(form.store, (s) => s.values.type);
  const authMethod = useStore(form.store, (s) => s.values.auth_method);
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
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
                disabled={isEdit}
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
            <form.Field name="auth_method">
              {(field) => (
                <Field>
                  <FieldLabel>Authentication Method</FieldLabel>
                  <Select
                    value={field.state.value}
                    onValueChange={(v) =>
                      field.handleChange(v as "password" | "private_key")
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="password">密码</SelectItem>
                      <SelectItem value="private_key">私钥</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              )}
            </form.Field>
            {authMethod === "password" ? (
              <form.Field name="password">
                {(field) => (
                  <Field>
                    <FieldLabel>Password</FieldLabel>
                    <Input
                      type="password"
                      placeholder={isEdit ? "留空保持当前密码" : ""}
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                  </Field>
                )}
              </form.Field>
            ) : (
              <form.Field name="private_key">
                {(field) => (
                  <Field>
                    <FieldLabel>Private Key</FieldLabel>
                    <Textarea
                      rows={6}
                      className="font-mono text-xs"
                      placeholder={
                        isEdit
                          ? "留空保持当前私钥"
                          : "粘贴 PEM 格式私钥内容..."
                      }
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pem,.key,.pub,.id_rsa,.id_ed25519"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        file.text().then((text) => field.handleChange(text));
                        e.target.value = "";
                      }}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-1"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Upload className="mr-1 h-3 w-3" />
                      上传密钥文件
                    </Button>
                  </Field>
                )}
              </form.Field>
            )}
          </>
        ) : (
          <>
            <form.Field
              name="kubeconfig"
              validators={
                isEdit
                  ? undefined
                  : {
                      onSubmit: ({ value }) =>
                        !value ? "Kubeconfig 不能为空" : undefined,
                    }
              }
            >
              {(field) => (
                <Field
                  data-invalid={
                    field.state.meta.errors.length > 0 || undefined
                  }
                >
                  <FieldLabel>Kubeconfig</FieldLabel>
                  <Textarea
                    placeholder={
                      isEdit
                        ? "Leave blank to keep current"
                        : "Paste kubeconfig YAML content here..."
                    }
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
                      placeholder={isEdit ? "Leave blank to keep current" : "Optional"}
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
                      placeholder={isEdit ? "Leave blank to keep current" : "default"}
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
        <Button type="submit" disabled={isPending}>
          {isPending
            ? isEdit ? "Saving..." : "Adding..."
            : isEdit ? "Save" : "Add"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function CreateConnectionDialog({ projectId }: { projectId?: string }) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        Add Connection
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Connection</DialogTitle>
        </DialogHeader>
        <ConnectionForm
          mode="create"
          projectId={projectId}
          onSuccess={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

export function EditConnectionDialog({
  connection,
  open,
  onOpenChange,
}: {
  connection: Connection;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit Connection</DialogTitle>
        </DialogHeader>
        <ConnectionForm
          mode="edit"
          connection={connection}
          onSuccess={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
