import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import { Eye, EyeOff } from "lucide-react";
import { createService, updateService } from "@/api/services";
import { serviceSchema } from "@/lib/schemas";
import type { Service } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  DialogClose,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
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

const SERVICE_GROUPS = {
  database: "数据库",
  monitoring: "监控 & 搜索",
} as const;

const SERVICE_CONFIGS: Record<
  string,
  { label: string; defaultPort: number; group: keyof typeof SERVICE_GROUPS }
> = {
  mysql: { label: "MySQL", defaultPort: 3306, group: "database" },
  postgresql: { label: "PostgreSQL", defaultPort: 5432, group: "database" },
  mongodb: { label: "MongoDB", defaultPort: 27017, group: "database" },
  redis: { label: "Redis", defaultPort: 6379, group: "database" },
  prometheus: { label: "Prometheus", defaultPort: 9090, group: "monitoring" },
  elasticsearch: { label: "Elasticsearch", defaultPort: 9200, group: "monitoring" },
};

type FormValues = {
  name: string;
  description: string;
  service_type: string;
  host: string;
  port: string;
  password: string;
  // Dynamic config fields
  username: string;
  database: string;
  use_tls: boolean;
};

export function ServiceForm({
  mode,
  service,
  onSuccess,
}: {
  mode: "create" | "edit";
  service?: Service;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = mode === "edit";
  const [showPassword, setShowPassword] = useState(false);

  const createMutation = useMutation({
    mutationFn: createService,
    onSuccess: () => {
      toast.success("服务已添加");
      queryClient.invalidateQueries({ queryKey: ["services"] });
      onSuccess();
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: Parameters<typeof updateService>[1]) =>
      updateService(service!.id, data),
    onSuccess: () => {
      toast.success("服务已更新");
      queryClient.invalidateQueries({ queryKey: ["services"] });
      onSuccess();
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const defaultValues: FormValues =
    isEdit && service
      ? {
          name: service.name,
          description: service.description ?? "",
          service_type: service.service_type,
          host: service.host,
          port: String(service.port),
          password: "",
          username: (service.config.username as string) ?? "",
          database: (service.config.database as string) ?? "",
          use_tls: (service.config.use_tls as boolean) ?? false,
        }
      : {
          name: "",
          description: "",
          service_type: "mysql",
          host: "",
          port: "3306",
          password: "",
          username: "",
          database: "",
          use_tls: false,
        };

  const form = useForm({
    defaultValues,
    onSubmit: ({ value }) => {
      const config: Record<string, unknown> = {};
      if (value.username) config.username = value.username;
      if (value.database) config.database = value.database;
      if (value.use_tls) config.use_tls = value.use_tls;

      if (isEdit) {
        const data: Record<string, unknown> = {};
        if (value.name !== service!.name) data.name = value.name;
        if ((value.description || "") !== (service!.description || ""))
          data.description = value.description || undefined;
        if (value.host !== service!.host) data.host = value.host;
        if (parseInt(value.port) !== service!.port)
          data.port = parseInt(value.port);
        if (value.password) data.password = value.password;
        data.config = config;

        if (Object.keys(data).length === 0) {
          onSuccess();
          return;
        }
        updateMutation.mutate(data as Parameters<typeof updateService>[1]);
        return;
      }

      // Create mode
      const payload = {
        name: value.name,
        description: value.description || undefined,
        service_type: value.service_type,
        host: value.host,
        port: parseInt(value.port),
        password: value.password || undefined,
        config,
      };

      const result = serviceSchema.safeParse(payload);
      if (!result.success) {
        for (const issue of result.error.issues) {
          const path = issue.path?.[0]?.toString();
          if (path && path in form.state.values) {
            form.setFieldMeta(
              path as keyof typeof form.state.values,
              (prev) => ({
                ...prev,
                errorMap: { ...prev.errorMap, onSubmit: issue.message },
              }),
            );
          }
        }
        return;
      }

      createMutation.mutate(payload);
    },
  });

  const serviceType = useStore(form.store, (s) => s.values.service_type);
  const showUsername = ["mysql", "postgresql", "mongodb", "elasticsearch"].includes(serviceType);
  const showDatabase = [
    "mysql",
    "postgresql",
    "mongodb",
    "redis",
  ].includes(serviceType);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        form.handleSubmit();
      }}
    >
      <div className="space-y-4">
        <form.Field name="service_type">
          {(field) => (
            <Field>
              <FieldLabel>服务类型</FieldLabel>
              <Select
                value={field.state.value}
                onValueChange={(v) => {
                  if (v == null) return;
                  field.handleChange(v);
                  const cfg = SERVICE_CONFIGS[v as keyof typeof SERVICE_CONFIGS];
                  if (cfg) {
                    form.setFieldValue("port", String(cfg.defaultPort));
                  }
                }}
                disabled={isEdit}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择服务类型">
                    {SERVICE_CONFIGS[field.state.value]?.label ?? field.state.value}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(SERVICE_GROUPS).map(([groupKey, groupLabel]) => (
                    <SelectGroup key={groupKey}>
                      <SelectLabel>{groupLabel}</SelectLabel>
                      {Object.entries(SERVICE_CONFIGS)
                        .filter(([, cfg]) => cfg.group === groupKey)
                        .map(([key, cfg]) => (
                          <SelectItem key={key} value={key}>
                            {cfg.label}
                          </SelectItem>
                        ))}
                    </SelectGroup>
                  ))}
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
              data-invalid={field.state.meta.errors.length > 0 || undefined}
            >
              <FieldLabel>名称</FieldLabel>
              <Input
                placeholder="例如: 生产数据库"
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
                rows={2}
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
                data-invalid={field.state.meta.errors.length > 0 || undefined}
              >
                <FieldLabel>主机</FieldLabel>
                <Input
                  placeholder="e.g. 192.168.1.1"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                  onBlur={field.handleBlur}
                />
                <FieldError errors={fieldError(field.state.meta.errors)} />
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

        {showUsername && (
          <form.Field name="username">
            {(field) => (
              <Field>
                <FieldLabel>用户名</FieldLabel>
                <Input
                  placeholder="数据库用户名"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                />
              </Field>
            )}
          </form.Field>
        )}

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
                <p className="text-xs text-muted-foreground">
                  留空保持当前密码
                </p>
              )}
            </Field>
          )}
        </form.Field>

        {showDatabase && (
          <form.Field name="database">
            {(field) => (
              <Field>
                <FieldLabel>
                  {serviceType === "redis" ? "数据库编号" : "数据库名"}
                </FieldLabel>
                <Input
                  placeholder={
                    serviceType === "redis" ? "0" : "数据库名称"
                  }
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                />
              </Field>
            )}
          </form.Field>
        )}
      </div>
      <DialogFooter className="mt-4">
        <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
        <Button type="submit" disabled={isPending}>
          {isPending
            ? isEdit
              ? "保存中..."
              : "添加中..."
            : isEdit
              ? "保存"
              : "添加"}
        </Button>
      </DialogFooter>
    </form>
  );
}
