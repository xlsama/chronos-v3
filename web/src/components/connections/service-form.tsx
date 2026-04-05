import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import { Eye, EyeOff } from "lucide-react";
import { ServiceIcon } from "@/lib/service-icons";
import { client, orpc } from "@/lib/orpc";
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
import { Switch } from "@/components/ui/switch";

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
  analytics: "分析型数据库",
  monitoring: "监控 & 搜索",
  devops: "DevOps 工具",
} as const;

const SERVICE_CONFIGS: Record<
  string,
  { label: string; defaultPort: number; group: keyof typeof SERVICE_GROUPS }
> = {
  mysql: { label: "MySQL", defaultPort: 3306, group: "database" },
  postgresql: { label: "PostgreSQL", defaultPort: 5432, group: "database" },
  mongodb: { label: "MongoDB", defaultPort: 27017, group: "database" },
  redis: { label: "Redis", defaultPort: 6379, group: "database" },
  doris: { label: "Apache Doris", defaultPort: 9030, group: "analytics" },
  starrocks: { label: "StarRocks", defaultPort: 9030, group: "analytics" },
  hive: { label: "Apache Hive", defaultPort: 10000, group: "analytics" },
  prometheus: { label: "Prometheus", defaultPort: 9090, group: "monitoring" },
  elasticsearch: { label: "Elasticsearch", defaultPort: 9200, group: "monitoring" },
  jenkins: { label: "Jenkins", defaultPort: 8080, group: "devops" },
  kettle: { label: "Kettle (Carte)", defaultPort: 8181, group: "devops" },
  docker: { label: "Docker", defaultPort: 2376, group: "devops" },
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
  path: string;
};

export function ServiceForm({
  mode,
  service,
  onSuccess,
  onSubmitOverride,
  initialPassword,
}: {
  mode: "create" | "edit";
  service?: Service;
  onSuccess: () => void;
  onSubmitOverride?: (data: {
    name: string;
    description?: string;
    serviceType: string;
    host: string;
    port: number;
    password?: string;
    config?: Record<string, unknown>;
  }) => void;
  initialPassword?: string;
}) {
  const queryClient = useQueryClient();
  const isEdit = mode === "edit";
  const [showPassword, setShowPassword] = useState(false);

  const createMutation = useMutation({
    mutationFn: (data: Parameters<typeof client.service.create>[0]) => client.service.create(data),
    onSuccess: () => {
      toast.success("服务已添加");
      queryClient.invalidateQueries({ queryKey: orpc.service.list.key() });
      onSuccess();
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Parameters<typeof client.service.create>[0]>) =>
      client.service.update({ id: service!.id, ...data }),
    onSuccess: () => {
      toast.success("服务已更新");
      queryClient.invalidateQueries({ queryKey: orpc.service.list.key() });
      onSuccess();
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const defaultValues: FormValues =
    isEdit && service
      ? {
          name: service.name,
          description: service.description ?? "",
          service_type: service.serviceType,
          host: service.host,
          port: String(service.port),
          password: initialPassword ?? "",
          username: (service.config.username as string) ?? "",
          database: (service.config.database as string) ?? "",
          use_tls: (service.config.use_tls as boolean) ?? false,
          path: (service.config.path as string) ?? "",
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
          path: "",
        };

  const form = useForm({
    defaultValues,
    onSubmit: ({ value }) => {
      const config: Record<string, unknown> = {};
      if (value.username) config.username = value.username;
      if (value.database) config.database = value.database;
      if (value.use_tls) config.use_tls = value.use_tls;
      if (value.path) config.path = value.path;

      // onSubmitOverride 优先（用于导入编辑等场景）
      if (onSubmitOverride) {
        const payload = {
          name: value.name,
          description: value.description || undefined,
          serviceType: value.service_type,
          host: value.host,
          port: parseInt(value.port),
          password: value.password || undefined,
          config,
        };
        onSubmitOverride(payload);
        onSuccess();
        return;
      }

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
        updateMutation.mutate(data as Partial<Parameters<typeof client.service.create>[0]>);
        return;
      }

      // Create mode
      const payload = {
        name: value.name,
        description: value.description || undefined,
        serviceType: value.service_type,
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
  const showUsername = ["mysql", "postgresql", "mongodb", "elasticsearch", "doris", "starrocks", "jenkins", "kettle", "prometheus", "hive"].includes(serviceType);
  const showDatabase = [
    "mysql",
    "postgresql",
    "mongodb",
    "redis",
    "doris",
    "starrocks",
    "hive",
  ].includes(serviceType);
  const showPath = ["prometheus", "jenkins"].includes(serviceType);
  const showTLS = ["prometheus", "elasticsearch", "jenkins", "kettle", "docker"].includes(serviceType);

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
                    <ServiceIcon serviceType={field.state.value} className="h-4 w-4" />
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
                            <ServiceIcon serviceType={key} className="h-4 w-4" />
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
                  placeholder={
                    serviceType === "jenkins"
                      ? "Jenkins 用户名"
                      : serviceType === "kettle"
                        ? "Carte 用户名"
                        : serviceType === "elasticsearch"
                          ? "Elasticsearch 用户名"
                          : serviceType === "prometheus"
                            ? "用户名（可选）"
                            : serviceType === "hive"
                              ? "HiveServer2 用户名"
                              : "数据库用户名"
                  }
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
              <FieldLabel>{serviceType === "jenkins" ? "密码 / API Token" : "密码"}</FieldLabel>
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

        {showPath && (
          <form.Field name="path">
            {(field) => (
              <Field>
                <FieldLabel>API 路径</FieldLabel>
                <Input
                  placeholder={serviceType === "jenkins" ? "例如: /jenkins" : "例如: /prometheus"}
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  反向代理路径前缀（可选）
                </p>
              </Field>
            )}
          </form.Field>
        )}

        {showTLS && (
          <form.Field name="use_tls">
            {(field) => (
              <Field>
                <div className="flex items-center justify-between">
                  <FieldLabel>启用 TLS</FieldLabel>
                  <Switch
                    checked={field.state.value}
                    onCheckedChange={(v) => field.handleChange(v)}
                  />
                </div>
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
