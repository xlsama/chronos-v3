import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import { Upload, Eye, EyeOff, FileKey2 } from "lucide-react";
import { createServer, updateServer } from "@/api/servers";
import { serverSchema } from "@/lib/schemas";
import type { Server } from "@/lib/types";
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
import { Checkbox } from "@/components/ui/checkbox";

function fieldError(errors: unknown[]) {
  return errors.map((e) => ({
    message:
      typeof e === "string"
        ? e
        : (e as { message?: string })?.message ?? String(e),
  }));
}

type FormValues = {
  name: string;
  description: string;
  host: string;
  port: string;
  username: string;
  auth_method: "password" | "private_key";
  password: string;
  private_key: string;
  use_bastion: boolean;
  bastion_host: string;
  bastion_port: string;
  bastion_username: string;
  bastion_auth_method: "password" | "private_key";
  bastion_password: string;
  bastion_private_key: string;
};

function ServerForm({
  mode,
  server,
  onSuccess,
}: {
  mode: "create" | "edit";
  server?: Server;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = mode === "edit";

  const createMutation = useMutation({
    mutationFn: createServer,
    onSuccess: () => {
      toast.success("服务器已添加");
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      onSuccess();
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: Parameters<typeof updateServer>[1]) =>
      updateServer(server!.id, data),
    onSuccess: () => {
      toast.success("服务器已更新");
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      onSuccess();
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const defaultValues: FormValues = isEdit && server
    ? {
        name: server.name,
        description: server.description ?? "",
        host: server.host,
        port: String(server.port),
        username: server.username,
        auth_method: server.auth_method === "private_key" ? "private_key" : "password",
        password: "",
        private_key: "",
        use_bastion: server.has_bastion,
        bastion_host: server.bastion_host ?? "",
        bastion_port: "22",
        bastion_username: "",
        bastion_auth_method: "password",
        bastion_password: "",
        bastion_private_key: "",
      }
    : {
        name: "",
        description: "",
        host: "",
        port: "22",
        username: "root",
        auth_method: "password",
        password: "",
        private_key: "",
        use_bastion: false,
        bastion_host: "",
        bastion_port: "22",
        bastion_username: "",
        bastion_auth_method: "password",
        bastion_password: "",
        bastion_private_key: "",
      };

  const form = useForm({
    defaultValues,
    onSubmit: ({ value }) => {
      if (isEdit) {
        const data: Record<string, unknown> = {};
        if (value.name !== server!.name) data.name = value.name;
        if ((value.description || "") !== (server!.description || ""))
          data.description = value.description || undefined;
        if (value.host !== server!.host) data.host = value.host;
        if (parseInt(value.port) !== server!.port) data.port = parseInt(value.port);
        if (value.username !== server!.username) data.username = value.username;

        if (value.auth_method === "password" && value.password) {
          data.password = value.password;
          data.private_key = null;
        } else if (value.auth_method === "private_key" && value.private_key) {
          data.private_key = value.private_key;
          data.password = null;
        }

        // Bastion fields
        if (value.use_bastion) {
          data.bastion_host = value.bastion_host || null;
          data.bastion_port = value.bastion_port ? parseInt(value.bastion_port) : null;
          data.bastion_username = value.bastion_username || null;
          if (value.bastion_auth_method === "password" && value.bastion_password) {
            data.bastion_password = value.bastion_password;
            data.bastion_private_key = null;
          } else if (value.bastion_auth_method === "private_key" && value.bastion_private_key) {
            data.bastion_private_key = value.bastion_private_key;
            data.bastion_password = null;
          }
        } else {
          data.bastion_host = null;
          data.bastion_port = null;
          data.bastion_username = null;
          data.bastion_password = null;
          data.bastion_private_key = null;
        }

        if (Object.keys(data).length === 0) {
          onSuccess();
          return;
        }
        updateMutation.mutate(data as Parameters<typeof updateServer>[1]);
        return;
      }

      // Create mode - use zod validation
      const payload = {
        name: value.name,
        description: value.description || undefined,
        host: value.host,
        port: parseInt(value.port),
        username: value.username,
        auth_method: value.auth_method,
        ...(value.auth_method === "password"
          ? { password: value.password || undefined }
          : { private_key: value.private_key || undefined }),
        use_bastion: value.use_bastion,
        ...(value.use_bastion
          ? {
              bastion_host: value.bastion_host || undefined,
              bastion_port: value.bastion_port ? parseInt(value.bastion_port) : undefined,
              bastion_username: value.bastion_username || undefined,
              bastion_auth_method: value.bastion_auth_method,
              ...(value.bastion_auth_method === "password"
                ? { bastion_password: value.bastion_password || undefined }
                : { bastion_private_key: value.bastion_private_key || undefined }),
            }
          : {}),
      };

      const result = serverSchema.safeParse(payload);
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

      // Build API payload (strip use_bastion, auth_method, bastion_auth_method)
      const { use_bastion, auth_method, bastion_auth_method, ...apiData } = result.data;
      const apiPayload = {
        ...apiData,
        ...(use_bastion
          ? {}
          : {
              bastion_host: undefined,
              bastion_port: undefined,
              bastion_username: undefined,
              bastion_password: undefined,
              bastion_private_key: undefined,
            }),
      };
      createMutation.mutate(apiPayload);
    },
  });

  const authMethod = useStore(form.store, (s) => s.values.auth_method);
  const useBastion = useStore(form.store, (s) => s.values.use_bastion);
  const bastionAuthMethod = useStore(form.store, (s) => s.values.bastion_auth_method);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bastionFileInputRef = useRef<HTMLInputElement>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showBastionPassword, setShowBastionPassword] = useState(false);

  return (
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
                placeholder="例如: 生产服务器"
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
              <FieldLabel>描述</FieldLabel>
              <Textarea
                placeholder="用途说明"
                rows={3}
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
              />
            </Field>
          )}
        </form.Field>

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
                <FieldLabel>主机</FieldLabel>
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
                <FieldLabel>端口</FieldLabel>
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
              <FieldLabel>用户名</FieldLabel>
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
              <FieldLabel>认证方式</FieldLabel>
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
                <FieldLabel>密码</FieldLabel>
                <div className="relative">
                  <Input
                    type={showPassword ? "text" : "password"}
                    placeholder={isEdit ? "••••••••" : ""}
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    className="pr-9"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    onClick={() => setShowPassword(!showPassword)}
                    tabIndex={-1}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
                {isEdit && !field.state.value && (
                  <p className="text-xs text-muted-foreground">留空保持当前密码</p>
                )}
              </Field>
            )}
          </form.Field>
        ) : (
          <form.Field name="private_key">
            {(field) => (
              <Field>
                <FieldLabel>私钥</FieldLabel>
                {isEdit && !field.state.value && (
                  <div className="flex items-center gap-2 rounded-md border p-2 text-sm text-muted-foreground">
                    <FileKey2 className="h-4 w-4" />
                    <span>已配置私钥，留空保持不变</span>
                  </div>
                )}
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

        {/* Bastion / Jump Host */}
        <div className="border-t pt-4">
          <form.Field name="use_bastion">
            {(field) => (
              <label className="flex items-center gap-2 cursor-pointer">
                <Checkbox
                  checked={field.state.value}
                  onCheckedChange={(checked) => field.handleChange(!!checked)}
                />
                <span className="text-sm font-medium">需要通过跳板机连接</span>
              </label>
            )}
          </form.Field>
        </div>

        {useBastion && (
          <div className="space-y-4 rounded-md border p-4">
            <p className="text-xs font-medium text-muted-foreground">跳板机配置</p>
            <div className="flex gap-3">
              <form.Field
                name="bastion_host"
                validators={{
                  onSubmit: ({ value }) => {
                    const ub = form.getFieldValue("use_bastion");
                    return ub && !value ? "跳板机地址不能为空" : undefined;
                  },
                }}
              >
                {(field) => (
                  <Field
                    className="flex-1"
                    data-invalid={field.state.meta.errors.length > 0 || undefined}
                  >
                    <FieldLabel>跳板机地址</FieldLabel>
                    <Input
                      placeholder="e.g. bastion.example.com"
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                      onBlur={field.handleBlur}
                    />
                    <FieldError errors={fieldError(field.state.meta.errors)} />
                  </Field>
                )}
              </form.Field>
              <form.Field name="bastion_port">
                {(field) => (
                  <Field className="w-24">
                    <FieldLabel>端口</FieldLabel>
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
              name="bastion_username"
              validators={{
                onSubmit: ({ value }) => {
                  const ub = form.getFieldValue("use_bastion");
                  return ub && !value ? "跳板机用户名不能为空" : undefined;
                },
              }}
            >
              {(field) => (
                <Field data-invalid={field.state.meta.errors.length > 0 || undefined}>
                  <FieldLabel>用户名</FieldLabel>
                  <Input
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    onBlur={field.handleBlur}
                  />
                  <FieldError errors={fieldError(field.state.meta.errors)} />
                </Field>
              )}
            </form.Field>
            <form.Field name="bastion_auth_method">
              {(field) => (
                <Field>
                  <FieldLabel>认证方式</FieldLabel>
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
            {bastionAuthMethod === "password" ? (
              <form.Field name="bastion_password">
                {(field) => (
                  <Field>
                    <FieldLabel>密码</FieldLabel>
                    <div className="relative">
                      <Input
                        type={showBastionPassword ? "text" : "password"}
                        placeholder={isEdit ? "••••••••" : ""}
                        value={field.state.value}
                        onChange={(e) => field.handleChange(e.target.value)}
                        className="pr-9"
                      />
                      <button
                        type="button"
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        onClick={() => setShowBastionPassword(!showBastionPassword)}
                        tabIndex={-1}
                      >
                        {showBastionPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    {isEdit && !field.state.value && (
                      <p className="text-xs text-muted-foreground">留空保持当前密码</p>
                    )}
                  </Field>
                )}
              </form.Field>
            ) : (
              <form.Field name="bastion_private_key">
                {(field) => (
                  <Field>
                    <FieldLabel>私钥</FieldLabel>
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
                      ref={bastionFileInputRef}
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
                      onClick={() => bastionFileInputRef.current?.click()}
                    >
                      <Upload className="mr-1 h-3 w-3" />
                      上传密钥文件
                    </Button>
                  </Field>
                )}
              </form.Field>
            )}
          </div>
        )}
      </div>
      <DialogFooter className="mt-4">
        <DialogClose render={<Button variant="outline" />}>
          取消
        </DialogClose>
        <Button type="submit" disabled={isPending}>
          {isPending
            ? isEdit ? "保存中..." : "添加中..."
            : isEdit ? "保存" : "添加"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function CreateServerDialog() {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        添加服务器
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>添加服务器</DialogTitle>
        </DialogHeader>
        <ServerForm
          mode="create"
          onSuccess={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

export function EditServerDialog({
  server,
  open,
  onOpenChange,
}: {
  server: Server;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>编辑服务器</DialogTitle>
        </DialogHeader>
        <ServerForm
          mode="edit"
          server={server}
          onSuccess={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
