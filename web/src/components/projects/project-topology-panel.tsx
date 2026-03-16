import { useCallback, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LayoutGrid, Plus, Search } from "lucide-react";
import type { Connection as FlowConnection, Edge, Node } from "@xyflow/react";
import { deleteConnection } from "@/api/connections";
import { createServiceBinding, deleteServiceBinding } from "@/api/service-bindings";
import { createServiceDependency, deleteServiceDependency } from "@/api/service-dependencies";
import { getProjectTopology } from "@/api/projects";
import { createService, deleteService, discoverServices } from "@/api/services";
import type {
  Connection,
  Project,
  Service,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
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
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { CreateConnectionDialog } from "@/components/connections/create-connection-dialog";
import { TopologyGraph, useTopologyGraph } from "./topology-graph";

const SERVICE_TYPES = [
  "frontend",
  "backend_api",
  "worker",
  "etl_job",
  "cron_job",
  "database",
  "cache",
  "message_queue",
  "custom",
];

const DEPENDENCY_TYPES = [
  "api_call",
  "reads_from",
  "writes_to",
  "async_produces",
  "async_consumes",
  "scheduled_by",
];

const USAGE_TYPES = [
  "runtime_inspect",
  "logs",
  "db_access",
  "metrics",
  "http_probe",
];

function invalidateTopology(queryClient: ReturnType<typeof useQueryClient>, projectId: string) {
  queryClient.invalidateQueries({ queryKey: ["project-topology", projectId] });
  queryClient.invalidateQueries({ queryKey: ["connections"] });
}

// ── Create Service Dialog ──

function CreateServiceButton({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [serviceType, setServiceType] = useState("backend_api");
  const [description, setDescription] = useState("");
  const [businessContext, setBusinessContext] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createService,
    onSuccess: () => {
      toast.success("Service created");
      invalidateTopology(queryClient, projectId);
      setOpen(false);
      setName("");
      setDescription("");
      setBusinessContext("");
      setServiceType("backend_api");
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Plus className="mr-1 h-4 w-4" />
        Add Service
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Service</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel>Name</FieldLabel>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel>Type</FieldLabel>
            <Select value={serviceType} onValueChange={(value) => setServiceType(value ?? "backend_api")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SERVICE_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel>Description</FieldLabel>
            <Textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Business Context</FieldLabel>
            <Textarea
              rows={3}
              value={businessContext}
              onChange={(e) => setBusinessContext(e.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <Button
            onClick={() =>
              mutation.mutate({
                project_id: projectId,
                name,
                service_type: serviceType,
                description: description || undefined,
                business_context: businessContext || undefined,
              })
            }
            disabled={mutation.isPending || !name.trim()}
          >
            {mutation.isPending ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Create Dependency Dialog ──

function CreateDependencyDialog({
  projectId,
  services,
  defaultFromId,
  defaultToId,
  open,
  onOpenChange,
}: {
  projectId: string;
  services: Service[];
  defaultFromId?: string;
  defaultToId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [fromServiceId, setFromServiceId] = useState(defaultFromId ?? "");
  const [toServiceId, setToServiceId] = useState(defaultToId ?? "");
  const [dependencyType, setDependencyType] = useState("api_call");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createServiceDependency,
    onSuccess: () => {
      toast.success("Dependency created");
      invalidateTopology(queryClient, projectId);
      onOpenChange(false);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Service Dependency</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel>From Service</FieldLabel>
            <Select value={fromServiceId} onValueChange={(value) => setFromServiceId(value ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Choose source service" />
              </SelectTrigger>
              <SelectContent>
                {services.map((service) => (
                  <SelectItem key={service.id} value={service.id}>
                    {service.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel>To Service</FieldLabel>
            <Select value={toServiceId} onValueChange={(value) => setToServiceId(value ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Choose target service" />
              </SelectTrigger>
              <SelectContent>
                {services.map((service) => (
                  <SelectItem key={service.id} value={service.id}>
                    {service.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel>Dependency Type</FieldLabel>
            <Select value={dependencyType} onValueChange={(value) => setDependencyType(value ?? "api_call")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEPENDENCY_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel>Description</FieldLabel>
            <Textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <Button
            onClick={() =>
              mutation.mutate({
                project_id: projectId,
                from_service_id: fromServiceId,
                to_service_id: toServiceId,
                dependency_type: dependencyType,
                description: description || undefined,
              })
            }
            disabled={mutation.isPending || !fromServiceId || !toServiceId}
          >
            {mutation.isPending ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Create Binding Dialog ──

function CreateBindingDialog({
  projectId,
  services,
  connections,
  defaultServiceId,
  defaultConnectionId,
  open,
  onOpenChange,
}: {
  projectId: string;
  services: Service[];
  connections: Connection[];
  defaultServiceId?: string;
  defaultConnectionId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [serviceId, setServiceId] = useState(defaultServiceId ?? "");
  const [connectionId, setConnectionId] = useState(defaultConnectionId ?? "");
  const [usageType, setUsageType] = useState("runtime_inspect");
  const [priority, setPriority] = useState("100");
  const [notes, setNotes] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createServiceBinding,
    onSuccess: () => {
      toast.success("Binding created");
      invalidateTopology(queryClient, projectId);
      onOpenChange(false);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Service Binding</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel>Service</FieldLabel>
            <Select value={serviceId} onValueChange={(value) => setServiceId(value ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Choose service" />
              </SelectTrigger>
              <SelectContent>
                {services.map((service) => (
                  <SelectItem key={service.id} value={service.id}>
                    {service.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel>Connection</FieldLabel>
            <Select value={connectionId} onValueChange={(value) => setConnectionId(value ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Choose connection" />
              </SelectTrigger>
              <SelectContent>
                {connections.map((connection) => (
                  <SelectItem key={connection.id} value={connection.id}>
                    {connection.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel>Usage</FieldLabel>
              <Select value={usageType} onValueChange={(value) => setUsageType(value ?? "runtime_inspect")}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {USAGE_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel>Priority</FieldLabel>
              <Input
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                type="number"
              />
            </Field>
          </div>
          <Field>
            <FieldLabel>Notes</FieldLabel>
            <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <Button
            onClick={() =>
              mutation.mutate({
                project_id: projectId,
                service_id: serviceId,
                connection_id: connectionId,
                usage_type: usageType,
                priority: Number(priority) || 100,
                notes: notes || undefined,
              })
            }
            disabled={mutation.isPending || !serviceId || !connectionId}
          >
            {mutation.isPending ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Context Menu ──

function ContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number;
  y: number;
  items: { label: string; onClick: () => void; variant?: "destructive" }[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div
        ref={ref}
        className="fixed z-50 rounded-md border bg-popover p-1 shadow-md"
        style={{ left: x, top: y }}
      >
        {items.map((item) => (
          <button
            key={item.label}
            className={`flex w-full items-center rounded-sm px-3 py-1.5 text-sm hover:bg-accent ${
              item.variant === "destructive" ? "text-destructive" : ""
            }`}
            onClick={() => {
              item.onClick();
              onClose();
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
    </>
  );
}

// ── Auto Layout Button ──

function AutoLayoutButton() {
  const { autoLayout } = useTopologyGraph();
  return (
    <Button size="sm" variant="outline" onClick={autoLayout}>
      <LayoutGrid className="mr-1 h-4 w-4" />
      Auto Layout
    </Button>
  );
}

// ── Discover Services Button ──

function DiscoverServicesButton({
  projectId,
  connections,
}: {
  projectId: string;
  connections: Connection[];
}) {
  const [open, setOpen] = useState(false);
  const [selectedConnId, setSelectedConnId] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: discoverServices,
    onSuccess: (data) => {
      toast.success(`Discovered ${data.discovered} services`);
      invalidateTopology(queryClient, projectId);
      setOpen(false);
    },
    onError: () => {
      toast.error("Discovery failed");
    },
  });

  if (!connections.length) return null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Search className="mr-1 h-4 w-4" />
        Discover Services
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Auto-discover Services</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Scan a connection for running services (Docker containers, systemd units, listening ports, cron jobs, K8s workloads).
        </p>
        <Field>
          <FieldLabel>Connection</FieldLabel>
          <Select value={selectedConnId} onValueChange={(value) => setSelectedConnId(value ?? "")}>
            <SelectTrigger>
              <SelectValue placeholder="Choose connection to scan" />
            </SelectTrigger>
            <SelectContent>
              {connections.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <Button
            onClick={() => mutation.mutate(selectedConnId)}
            disabled={mutation.isPending || !selectedConnId}
          >
            {mutation.isPending ? "Scanning..." : "Start Discovery"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Component ──

export function ProjectTopologyPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["project-topology", project.id],
    queryFn: () => getProjectTopology(project.id),
  });

  const services = data?.services ?? [];
  const connections = data?.connections ?? [];

  // Context menu state
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    items: { label: string; onClick: () => void; variant?: "destructive" }[];
  } | null>(null);

  // Dialog state for drag-to-connect
  const [depDialog, setDepDialog] = useState<{
    open: boolean;
    fromId?: string;
    toId?: string;
  }>({ open: false });
  const [bindDialog, setBindDialog] = useState<{
    open: boolean;
    serviceId?: string;
    connectionId?: string;
  }>({ open: false });

  // Delete mutations
  const serviceDelete = useMutation({
    mutationFn: deleteService,
    onSuccess: () => {
      toast.success("Service deleted");
      invalidateTopology(queryClient, project.id);
    },
  });
  const connectionDelete = useMutation({
    mutationFn: deleteConnection,
    onSuccess: () => {
      toast.success("Connection deleted");
      invalidateTopology(queryClient, project.id);
    },
  });
  const dependencyDelete = useMutation({
    mutationFn: deleteServiceDependency,
    onSuccess: () => {
      toast.success("Dependency deleted");
      invalidateTopology(queryClient, project.id);
    },
  });
  const bindingDelete = useMutation({
    mutationFn: deleteServiceBinding,
    onSuccess: () => {
      toast.success("Binding deleted");
      invalidateTopology(queryClient, project.id);
    },
  });

  const extractId = (nodeId: string) => nodeId.replace(/^(svc-|conn-)/, "");

  const handleConnect = useCallback(
    (params: FlowConnection) => {
      const sourceType = params.source?.startsWith("svc-") ? "service" : "connection";
      const targetType = params.target?.startsWith("svc-") ? "service" : "connection";

      if (sourceType === "service" && targetType === "service") {
        setDepDialog({
          open: true,
          fromId: extractId(params.source!),
          toId: extractId(params.target!),
        });
      } else if (sourceType === "service" && targetType === "connection") {
        setBindDialog({
          open: true,
          serviceId: extractId(params.source!),
          connectionId: extractId(params.target!),
        });
      } else if (sourceType === "connection" && targetType === "service") {
        setBindDialog({
          open: true,
          serviceId: extractId(params.target!),
          connectionId: extractId(params.source!),
        });
      }
    },
    [],
  );

  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      const isService = node.id.startsWith("svc-");
      const entityId = extractId(node.id);
      const label = isService ? "Delete Service" : "Delete Connection";

      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        items: [
          {
            label,
            variant: "destructive",
            onClick: () => {
              if (isService) serviceDelete.mutate(entityId);
              else connectionDelete.mutate(entityId);
            },
          },
        ],
      });
    },
    [serviceDelete, connectionDelete],
  );

  const handleEdgeContextMenu = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      const edgeData = edge.data as { entityType: string; entityId: string } | undefined;
      if (!edgeData) return;
      const label =
        edgeData.entityType === "dependency" ? "Delete Dependency" : "Delete Binding";

      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        items: [
          {
            label,
            variant: "destructive",
            onClick: () => {
              if (edgeData.entityType === "dependency") dependencyDelete.mutate(edgeData.entityId);
              else bindingDelete.mutate(edgeData.entityId);
            },
          },
        ],
      });
    },
    [dependencyDelete, bindingDelete],
  );

  if (isLoading) {
    return <Skeleton className="h-[500px] rounded-xl" />;
  }

  const hasContent = services.length > 0 || connections.length > 0;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <CreateServiceButton projectId={project.id} />
        <CreateConnectionDialog projectId={project.id} />
        <DiscoverServicesButton projectId={project.id} connections={connections} />
        {hasContent && (
          <div className="ml-auto flex items-center gap-2">
            <Badge variant="secondary">{services.length} services</Badge>
            <Badge variant="secondary">{connections.length} connections</Badge>
            <Badge variant="secondary">{data?.dependencies.length ?? 0} deps</Badge>
            <Badge variant="secondary">{data?.bindings.length ?? 0} bindings</Badge>
          </div>
        )}
      </div>

      {/* Graph */}
      {hasContent && data ? (
        <div className="h-[500px] rounded-xl border bg-muted/30">
          <TopologyGraph
            topology={data}
            onConnect={handleConnect}
            onNodeContextMenu={handleNodeContextMenu}
            onEdgeContextMenu={handleEdgeContextMenu}
          />
        </div>
      ) : (
        <div className="flex h-[300px] items-center justify-center rounded-xl border border-dashed">
          <div className="text-center text-muted-foreground">
            <p className="text-sm">No topology data yet.</p>
            <p className="text-xs mt-1">Add services and connections to build the topology graph.</p>
          </div>
        </div>
      )}

      {hasContent && (
        <p className="text-xs text-muted-foreground">
          Drag from one node to another to create relationships. Right-click nodes or edges to delete.
        </p>
      )}

      {/* Context menu */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenu.items}
          onClose={() => setContextMenu(null)}
        />
      )}

      {/* Dependency dialog (from drag connect) */}
      <CreateDependencyDialog
        projectId={project.id}
        services={services}
        defaultFromId={depDialog.fromId}
        defaultToId={depDialog.toId}
        open={depDialog.open}
        onOpenChange={(open) => setDepDialog((prev) => ({ ...prev, open }))}
      />

      {/* Binding dialog (from drag connect) */}
      <CreateBindingDialog
        projectId={project.id}
        services={services}
        connections={connections}
        defaultServiceId={bindDialog.serviceId}
        defaultConnectionId={bindDialog.connectionId}
        open={bindDialog.open}
        onOpenChange={(open) => setBindDialog((prev) => ({ ...prev, open }))}
      />
    </div>
  );
}
