import { useState, useCallback, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  FileSearch,
  Eye,
  Pencil,
  ArrowLeft,
  Loader2,
  Plug,
  Server,
  Database,
  AlertCircle,
} from "lucide-react";
import {
  importConnections,
  type ExtractedConnections,
  type ExtractedService,
  type ExtractedServer,
} from "@/api/projects";
import { client, orpc } from "@/lib/orpc";
import { ServiceIcon } from "@/lib/service-icons";
import { ServiceForm } from "@/components/connections/service-form";
import { ServerForm } from "@/components/servers/create-server-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import type { Service } from "@/lib/types";

// ── Completeness checks ──

function isServiceComplete(s: ExtractedService): boolean {
  return !!(s.name && s.service_type && s.host && s.port);
}

function isServerComplete(s: ExtractedServer): boolean {
  return !!(s.name && s.host);
}

// ── Service type labels ──

const SERVICE_TYPE_LABELS: Record<string, string> = {
  mysql: "MySQL",
  postgresql: "PostgreSQL",
  mongodb: "MongoDB",
  redis: "Redis",
  doris: "Apache Doris",
  starrocks: "StarRocks",
  hive: "Apache Hive",
  prometheus: "Prometheus",
  elasticsearch: "Elasticsearch",
  jenkins: "Jenkins",
  kettle: "Kettle",
  kubernetes: "Kubernetes",
  docker: "Docker",
};

// ── View JSON Dialog ──

function ViewJsonDialog({
  open,
  onOpenChange,
  data,
  title,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: unknown;
  title: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <pre className="rounded-md bg-muted p-3 text-xs overflow-auto max-h-80 font-mono">
            {JSON.stringify(data, null, 2)}
          </pre>
        </DialogBody>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>关闭</DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Component ──

type ViewState = "idle" | "loading" | "results" | "editing";

export function ImportConnectionsButton({
  projectId,
}: {
  projectId: string;
}) {
  const queryClient = useQueryClient();

  // State
  const [showConfirm, setShowConfirm] = useState(false);
  const [view, setView] = useState<ViewState>("idle");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [extractedData, setExtractedData] =
    useState<ExtractedConnections | null>(null);
  const [selectedServices, setSelectedServices] = useState<Set<number>>(
    new Set(),
  );
  const [selectedServers, setSelectedServers] = useState<Set<number>>(
    new Set(),
  );
  const [editTarget, setEditTarget] = useState<{
    type: "service" | "server";
    index: number;
  } | null>(null);
  const [viewJson, setViewJson] = useState<{
    data: unknown;
    title: string;
  } | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [testingItems, setTestingItems] = useState<Set<string>>(new Set());
  const abortControllerRef = useRef<AbortController | null>(null);

  // Extract mutation
  const extractMutation = useMutation({
    mutationFn: () => {
      const controller = new AbortController();
      abortControllerRef.current = controller;
      return importConnections(projectId, controller.signal);
    },
    onSuccess: (data) => {
      abortControllerRef.current = null;
      setExtractedData(data);
      // Auto-select complete items (skip already-existing ones)
      const svcSet = new Set<number>();
      data.services.forEach((s, i) => {
        if (isServiceComplete(s) && !s.existing_name) svcSet.add(i);
      });
      setSelectedServices(svcSet);
      const srvSet = new Set<number>();
      data.servers.forEach((s, i) => {
        if (isServerComplete(s) && !s.existing_name) srvSet.add(i);
      });
      setSelectedServers(srvSet);
      setView("results");
    },
    onError: () => {
      const wasAborted = abortControllerRef.current?.signal.aborted;
      abortControllerRef.current = null;
      if (wasAborted) return;
      setDialogOpen(false);
      setView("idle");
    },
  });

  // Import mutation
  const importMutation = useMutation({
    mutationFn: async () => {
      if (!extractedData) return;

      const serviceItems = [...selectedServices].map((i) => {
        const s = extractedData.services[i];
        return {
          name: s.name,
          description: s.description ?? undefined,
          serviceType: s.service_type!,
          host: s.host!,
          port: s.port!,
          password: s.password ?? undefined,
          config: s.config ?? {},
        };
      });
      const serverItems = [...selectedServers].map((i) => {
        const s = extractedData.servers[i];
        return {
          name: s.name,
          description: s.description ?? undefined,
          host: s.host!,
          port: s.port ?? 22,
          username: s.username ?? "root",
          password: s.password ?? undefined,
        };
      });

      const results = await Promise.all([
        serviceItems.length > 0
          ? client.service.batchCreate({ items: serviceItems })
          : Promise.resolve(null),
        serverItems.length > 0
          ? client.server.batchCreate({ items: serverItems })
          : Promise.resolve(null),
      ]);
      return results;
    },
    onSuccess: (results) => {
      if (!results) return;
      const [svcResult, srvResult] = results;
      const created =
        (svcResult?.created ?? 0) + (srvResult?.created ?? 0);
      const skipped =
        (svcResult?.skipped ?? 0) + (srvResult?.skipped ?? 0);
      const errors = [
        ...(svcResult?.errors ?? []),
        ...(srvResult?.errors ?? []),
      ];

      if (errors.length > 0) {
        toast.warning(
          `导入完成：${created} 个成功，${skipped} 个跳过，${errors.length} 个失败`,
        );
      } else if (skipped > 0) {
        toast.success(`导入完成：${created} 个成功，${skipped} 个已存在跳过`);
      } else {
        toast.success(`成功导入 ${created} 个连接`);
      }

      queryClient.invalidateQueries({ queryKey: orpc.service.list.key() });
      queryClient.invalidateQueries({ queryKey: orpc.server.list.key() });
      handleClose();
    },
  });

  // Handlers
  const handleConfirm = useCallback(() => {
    setShowConfirm(false);
    setDialogOpen(true);
    setView("loading");
    extractMutation.mutate();
  }, [extractMutation]);

  const handleClose = useCallback(() => {
    setDialogOpen(false);
    setView("idle");
    setExtractedData(null);
    setSelectedServices(new Set());
    setSelectedServers(new Set());
    setEditTarget(null);
    setShowCancelConfirm(false);
    setTestingItems(new Set());
  }, []);

  const handleTestService = useCallback(
    async (index: number) => {
      if (!extractedData) return;
      const svc = extractedData.services[index];
      if (!svc.service_type || !svc.host || !svc.port) {
        toast.error("信息不完整，无法测试连接");
        return;
      }
      const key = `service-${index}`;
      setTestingItems((prev) => new Set([...prev, key]));
      try {
        const result = await client.service.testInline({
          serviceType: svc.service_type!,
          host: svc.host!,
          port: svc.port!,
          password: svc.password,
          config: svc.config ?? {},
        });
        if (result.success) {
          toast.success(`${svc.name} 连接测试成功`, { description: result.message });
        } else {
          toast.error(`${svc.name} 连接测试失败`, { description: result.message });
        }
      } catch {
        // request() already handles error toast
      } finally {
        setTestingItems((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [extractedData],
  );

  const handleTestServer = useCallback(
    async (index: number) => {
      if (!extractedData) return;
      const srv = extractedData.servers[index];
      if (!srv.host) {
        toast.error("信息不完整，无法测试连接");
        return;
      }
      const key = `server-${index}`;
      setTestingItems((prev) => new Set([...prev, key]));
      try {
        const result = await client.server.testInline({
          host: srv.host,
          port: srv.port ?? 22,
          username: srv.username ?? "root",
          password: srv.password,
        });
        if (result.success) {
          toast.success(`${srv.name} 连接测试成功`, { description: result.message });
        } else {
          toast.error(`${srv.name} 连接测试失败`, { description: result.message });
        }
      } catch {
        // request() already handles error toast
      } finally {
        setTestingItems((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [extractedData],
  );

  const handleCancelExtract = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    handleClose();
  }, [handleClose]);

  const handleEdit = useCallback(
    (type: "service" | "server", index: number) => {
      setEditTarget({ type, index });
      setView("editing");
    },
    [],
  );

  const handleEditSubmitService = useCallback(
    (data: {
      name: string;
      description?: string;
      serviceType: string;
      host: string;
      port: number;
      password?: string;
      config?: Record<string, unknown>;
    }) => {
      if (!extractedData || !editTarget) return;
      const updated = { ...extractedData };
      updated.services = [...updated.services];
      updated.services[editTarget.index] = {
        ...updated.services[editTarget.index],
        name: data.name,
        description: data.description ?? null,
        service_type: data.serviceType,
        host: data.host,
        port: data.port,
        password: data.password ?? null,
        config: data.config ?? {},
        existing_name: null,
      };
      setExtractedData(updated);
      // Auto-select if now complete
      if (isServiceComplete(updated.services[editTarget.index])) {
        setSelectedServices((prev) => new Set([...prev, editTarget.index]));
      }
    },
    [extractedData, editTarget],
  );

  const handleEditSubmitServer = useCallback(
    (data: {
      name: string;
      description?: string;
      host: string;
      port?: number;
      username?: string;
      password?: string;
    }) => {
      if (!extractedData || !editTarget) return;
      const updated = { ...extractedData };
      updated.servers = [...updated.servers];
      updated.servers[editTarget.index] = {
        ...updated.servers[editTarget.index],
        name: data.name,
        description: data.description ?? null,
        host: data.host,
        port: data.port ?? 22,
        username: data.username ?? "root",
        password: data.password ?? null,
        existing_name: null,
      };
      setExtractedData(updated);
      // Auto-select if now complete
      if (isServerComplete(updated.servers[editTarget.index])) {
        setSelectedServers((prev) => new Set([...prev, editTarget.index]));
      }
    },
    [extractedData, editTarget],
  );

  const toggleService = useCallback((index: number) => {
    setSelectedServices((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const toggleServer = useCallback((index: number) => {
    setSelectedServers((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const totalSelected = selectedServices.size + selectedServers.size;

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setShowConfirm(true)}
      >
        <FileSearch className="mr-1.5 h-4 w-4" />
        从文档导入连接
      </Button>

      {/* Confirmation AlertDialog */}
      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>从文档提取连接信息</AlertDialogTitle>
            <AlertDialogDescription>
              是否提取当前项目所有文档中的服务和服务器信息，自动导入？
              此操作将使用 AI 分析文档内容，可能需要一些时间。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirm}>
              确认提取
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Main Dialog */}
      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          if (!open && view !== "loading") handleClose();
        }}
      >
        <DialogContent
          className="sm:max-w-3xl"
          showCloseButton={view !== "loading"}
        >
          {/* Loading View */}
          {view === "loading" && (
            <>
              <DialogHeader>
                <DialogTitle>正在分析文档</DialogTitle>
              </DialogHeader>
              <DialogBody>
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  <div className="text-center">
                    <p className="text-sm font-medium">正在解析文档内容...</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      AI 正在从文档中提取服务和服务器信息，请稍候
                    </p>
                  </div>
                </div>
              </DialogBody>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setShowCancelConfirm(true)}
                >
                  取消分析
                </Button>
              </DialogFooter>
            </>
          )}

          {/* Results View */}
          {view === "results" && extractedData && (
            <>
              <DialogHeader>
                <DialogTitle>提取结果</DialogTitle>
              </DialogHeader>
              <DialogBody>
                <div className="space-y-6">
                  {extractedData.warnings.length > 0 && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200">
                      <div className="mb-2 flex items-center gap-2 font-medium">
                        <AlertCircle className="h-4 w-4" />
                        导入提示
                      </div>
                      <div className="space-y-1 text-xs leading-5">
                        {extractedData.warnings.map((warning, index) => (
                          <p key={index}>{warning}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Services Section */}
                  {extractedData.services.length > 0 && (
                    <div>
                      <div className="mb-3 flex items-center gap-2">
                        <Database className="h-4 w-4 text-muted-foreground" />
                        <h3 className="text-sm font-medium">
                          服务（{extractedData.services.length}）
                        </h3>
                      </div>
                      <div className="space-y-2">
                        {extractedData.services.map((svc, i) => {
                          const complete = isServiceComplete(svc);
                          const isExisting = !!svc.existing_name;
                          const canSelect = complete && !isExisting;
                          return (
                            <div
                              key={i}
                              className={`flex items-center gap-3 rounded-lg border p-3 ${!canSelect ? "opacity-60" : "cursor-pointer"}`}
                              onClick={() => canSelect && toggleService(i)}
                            >
                              <Checkbox
                                checked={selectedServices.has(i)}
                                onCheckedChange={() => toggleService(i)}
                                disabled={!canSelect}
                              />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  {svc.service_type && (
                                    <ServiceIcon
                                      serviceType={svc.service_type}
                                      className="h-4 w-4"
                                    />
                                  )}
                                  <span className="text-sm font-medium truncate">
                                    {svc.name}
                                  </span>
                                  {svc.service_type && (
                                    <span className="text-xs text-muted-foreground">
                                      {SERVICE_TYPE_LABELS[svc.service_type] ??
                                        svc.service_type}
                                    </span>
                                  )}
                                </div>
                                <div className="mt-0.5 text-xs text-muted-foreground">
                                  {svc.host
                                    ? `${svc.host}${svc.port ? `:${svc.port}` : ""}`
                                    : "未知地址"}
                                </div>
                                {isExisting && (
                                  <div className="mt-1 flex items-center gap-1 text-xs text-emerald-600">
                                    <AlertCircle className="h-3 w-3" />
                                    已导入，对应：{svc.existing_name}
                                  </div>
                                )}
                                {!isExisting && !complete && (
                                  <div className="mt-1 flex items-center gap-1 text-xs text-amber-600">
                                    <AlertCircle className="h-3 w-3" />
                                    信息不完整，请点击编辑补充
                                  </div>
                                )}
                                {!isExisting && complete && !svc.password && (
                                  <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                                    <AlertCircle className="h-3 w-3" />
                                    未检测到密码，可点击编辑补充。即使这里连通，仍不代表业务平台在线。
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  onClick={() =>
                                    setViewJson({
                                      data: svc,
                                      title: `服务: ${svc.name}`,
                                    })
                                  }
                                >
                                  <Eye className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  onClick={() => handleEdit("service", i)}
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  onClick={() => handleTestService(i)}
                                  disabled={!complete || testingItems.has(`service-${i}`)}
                                >
                                  {testingItems.has(`service-${i}`) ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Plug className="h-3.5 w-3.5" />
                                  )}
                                </Button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Servers Section */}
                  {extractedData.servers.length > 0 && (
                    <div>
                      <div className="mb-3 flex items-center gap-2">
                        <Server className="h-4 w-4 text-muted-foreground" />
                        <h3 className="text-sm font-medium">
                          服务器（{extractedData.servers.length}）
                        </h3>
                      </div>
                      <div className="space-y-2">
                        {extractedData.servers.map((srv, i) => {
                          const complete = isServerComplete(srv);
                          const isExisting = !!srv.existing_name;
                          const canSelect = complete && !isExisting;
                          return (
                            <div
                              key={i}
                              className={`flex items-center gap-3 rounded-lg border p-3 ${!canSelect ? "opacity-60" : "cursor-pointer"}`}
                              onClick={() => canSelect && toggleServer(i)}
                            >
                              <Checkbox
                                checked={selectedServers.has(i)}
                                onCheckedChange={() => toggleServer(i)}
                                disabled={!canSelect}
                              />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <Server className="h-4 w-4 text-muted-foreground" />
                                  <span className="text-sm font-medium truncate">
                                    {srv.name}
                                  </span>
                                </div>
                                <div className="mt-0.5 text-xs text-muted-foreground">
                                  {srv.host
                                    ? `${srv.username ?? "root"}@${srv.host}:${srv.port ?? 22}`
                                    : "未知地址"}
                                </div>
                                {isExisting && (
                                  <div className="mt-1 flex items-center gap-1 text-xs text-emerald-600">
                                    <AlertCircle className="h-3 w-3" />
                                    已导入，对应：{srv.existing_name}
                                  </div>
                                )}
                                {!isExisting && !complete && (
                                  <div className="mt-1 flex items-center gap-1 text-xs text-amber-600">
                                    <AlertCircle className="h-3 w-3" />
                                    信息不完整，请点击编辑补充
                                  </div>
                                )}
                                {!isExisting && complete && !srv.password && (
                                  <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                                    <AlertCircle className="h-3 w-3" />
                                    未检测到密码，可点击编辑补充
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  onClick={() =>
                                    setViewJson({
                                      data: srv,
                                      title: `服务器: ${srv.name}`,
                                    })
                                  }
                                >
                                  <Eye className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  onClick={() => handleEdit("server", i)}
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  onClick={() => handleTestServer(i)}
                                  disabled={!complete || testingItems.has(`server-${i}`)}
                                >
                                  {testingItems.has(`server-${i}`) ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Plug className="h-3.5 w-3.5" />
                                  )}
                                </Button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Empty State */}
                  {extractedData.services.length === 0 &&
                    extractedData.servers.length === 0 && (
                      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                        <FileSearch className="h-8 w-8 mb-3" />
                        <p className="text-sm">未从文档中检测到任何连接信息</p>
                      </div>
                    )}
                </div>
              </DialogBody>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>
                  取消
                </DialogClose>
                <Button
                  onClick={() => importMutation.mutate()}
                  disabled={totalSelected === 0 || importMutation.isPending}
                >
                  {importMutation.isPending
                    ? "导入中..."
                    : `导入选中 (${totalSelected})`}
                </Button>
              </DialogFooter>
            </>
          )}

          {/* Edit View */}
          {view === "editing" && editTarget && extractedData && (
            <>
              <DialogHeader>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => {
                      setView("results");
                      setEditTarget(null);
                    }}
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                  <DialogTitle>
                    编辑
                    {editTarget.type === "service" ? "服务" : "服务器"}
                  </DialogTitle>
                </div>
              </DialogHeader>
              {editTarget.type === "service" ? (
                <EditServiceView
                  service={extractedData.services[editTarget.index]}
                  onSubmit={handleEditSubmitService}
                  onBack={() => {
                    setView("results");
                    setEditTarget(null);
                  }}
                />
              ) : (
                <EditServerView
                  server={extractedData.servers[editTarget.index]}
                  onSubmit={handleEditSubmitServer}
                  onBack={() => {
                    setView("results");
                    setEditTarget(null);
                  }}
                />
              )}
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* View JSON Dialog */}
      {viewJson && (
        <ViewJsonDialog
          open={!!viewJson}
          onOpenChange={(open) => {
            if (!open) setViewJson(null);
          }}
          data={viewJson.data}
          title={viewJson.title}
        />
      )}

      {/* Cancel Extract Confirmation */}
      <AlertDialog
        open={showCancelConfirm}
        onOpenChange={setShowCancelConfirm}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>取消文档分析</AlertDialogTitle>
            <AlertDialogDescription>
              文档正在分析中，确定要取消吗？取消后需要重新发起分析。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>继续等待</AlertDialogCancel>
            <AlertDialogAction onClick={handleCancelExtract}>
              确认取消
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

// ── Edit Service View ──

function EditServiceView({
  service,
  onSubmit,
  onBack,
}: {
  service: ExtractedService;
  onSubmit: (data: {
    name: string;
    description?: string;
    serviceType: string;
    host: string;
    port: number;
    password?: string;
    config?: Record<string, unknown>;
  }) => void;
  onBack: () => void;
}) {
  // Build a temporary Service object for the form
  const tempService: Service = {
    id: "",
    name: service.name ?? "",
    description: service.description ?? null,
    serviceType: service.service_type ?? "mysql",
    host: service.host ?? "",
    port: service.port ?? 3306,
    config: service.config ?? {},
    hasPassword: !!service.password,
    status: "unknown",
    createdAt: "",
    updatedAt: "",
  };

  return (
    <ServiceForm
      mode="edit"
      service={tempService}
      onSuccess={onBack}
      onSubmitOverride={onSubmit}
      initialPassword={service.password ?? undefined}
    />
  );
}

// ── Edit Server View ──

function EditServerView({
  server,
  onSubmit,
  onBack,
}: {
  server: ExtractedServer;
  onSubmit: (data: {
    name: string;
    description?: string;
    host: string;
    port?: number;
    username?: string;
    password?: string;
  }) => void;
  onBack: () => void;
}) {
  // Build a temporary Server object for the form
  const tempServer = {
    id: "",
    name: server.name ?? "",
    description: server.description ?? null,
    host: server.host ?? "",
    port: server.port ?? 22,
    username: server.username ?? "root",
    status: "unknown",
    authMethod: "password" as const,
    hasBastion: false,
    bastionHost: null,
    createdAt: "",
    updatedAt: "",
  };

  return (
    <ServerForm
      mode="edit"
      server={tempServer}
      onSuccess={onBack}
      onSubmitOverride={onSubmit}
      initialPassword={server.password ?? undefined}
    />
  );
}
