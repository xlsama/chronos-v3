import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowRight, Link2, Plug, Plus, Trash2, Workflow } from "lucide-react";
import { deleteConnection } from "@/api/connections";
import { createServiceBinding, deleteServiceBinding } from "@/api/service-bindings";
import { createServiceDependency, deleteServiceDependency } from "@/api/service-dependencies";
import { getProjectTopology } from "@/api/projects";
import { createService, deleteService } from "@/api/services";
import type {
  Connection,
  Project,
  Service,
  ServiceConnectionBinding,
  ServiceDependency,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

function CreateDependencyButton({
  projectId,
  services,
}: {
  projectId: string;
  services: Service[];
}) {
  const [open, setOpen] = useState(false);
  const [fromServiceId, setFromServiceId] = useState("");
  const [toServiceId, setToServiceId] = useState("");
  const [dependencyType, setDependencyType] = useState("api_call");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createServiceDependency,
    onSuccess: () => {
      toast.success("Dependency created");
      invalidateTopology(queryClient, projectId);
      setOpen(false);
      setFromServiceId("");
      setToServiceId("");
      setDescription("");
      setDependencyType("api_call");
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Plus className="mr-1 h-4 w-4" />
        Add Dependency
      </DialogTrigger>
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

function CreateBindingButton({
  projectId,
  services,
  connections,
}: {
  projectId: string;
  services: Service[];
  connections: Connection[];
}) {
  const [open, setOpen] = useState(false);
  const [serviceId, setServiceId] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [usageType, setUsageType] = useState("runtime_inspect");
  const [priority, setPriority] = useState("100");
  const [notes, setNotes] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createServiceBinding,
    onSuccess: () => {
      toast.success("Binding created");
      invalidateTopology(queryClient, projectId);
      setOpen(false);
      setServiceId("");
      setConnectionId("");
      setUsageType("runtime_inspect");
      setPriority("100");
      setNotes("");
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Plus className="mr-1 h-4 w-4" />
        Bind Service
      </DialogTrigger>
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

function ServiceCard({
  service,
  onDelete,
}: {
  service: Service;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <p className="font-medium">{service.name}</p>
          <Badge variant="outline">{service.service_type}</Badge>
          <Badge variant="secondary">{service.source}</Badge>
        </div>
        {service.description && (
          <p className="text-sm text-muted-foreground">{service.description}</p>
        )}
        {service.business_context && (
          <p className="text-xs text-muted-foreground">{service.business_context}</p>
        )}
      </div>
      <Button variant="ghost" size="sm" onClick={() => onDelete(service.id)}>
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  );
}

function ConnectionCard({
  connection,
  onDelete,
}: {
  connection: Connection;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <p className="font-medium">{connection.name}</p>
          <Badge variant="outline">{connection.type}</Badge>
        </div>
        {connection.description && (
          <p className="text-sm text-muted-foreground">{connection.description}</p>
        )}
        <p className="text-xs text-muted-foreground">
          {connection.type === "kubernetes"
            ? "Kubernetes cluster"
            : `${connection.username}@${connection.host}:${connection.port}`}
        </p>
      </div>
      <Button variant="ghost" size="sm" onClick={() => onDelete(connection.id)}>
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  );
}

function BindingRow({
  binding,
  servicesById,
  connectionsById,
  onDelete,
}: {
  binding: ServiceConnectionBinding;
  servicesById: Record<string, Service>;
  connectionsById: Record<string, Connection>;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
      <div className="flex items-center gap-2 text-sm">
        <Link2 className="h-4 w-4 text-muted-foreground" />
        <span className="font-medium">{servicesById[binding.service_id]?.name ?? binding.service_id}</span>
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
        <span>{connectionsById[binding.connection_id]?.name ?? binding.connection_id}</span>
        <Badge variant="outline">{binding.usage_type}</Badge>
        <Badge variant="secondary">P{binding.priority}</Badge>
      </div>
      <Button variant="ghost" size="sm" onClick={() => onDelete(binding.id)}>
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  );
}

function DependencyRow({
  dependency,
  servicesById,
  onDelete,
}: {
  dependency: ServiceDependency;
  servicesById: Record<string, Service>;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
      <div className="flex items-center gap-2 text-sm">
        <Workflow className="h-4 w-4 text-muted-foreground" />
        <span className="font-medium">
          {servicesById[dependency.from_service_id]?.name ?? dependency.from_service_id}
        </span>
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
        <span>{servicesById[dependency.to_service_id]?.name ?? dependency.to_service_id}</span>
        <Badge variant="outline">{dependency.dependency_type}</Badge>
      </div>
      <Button variant="ghost" size="sm" onClick={() => onDelete(dependency.id)}>
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  );
}

export function ProjectTopologyPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["project-topology", project.id],
    queryFn: () => getProjectTopology(project.id),
  });

  const services = data?.services ?? [];
  const connections = data?.connections ?? [];
  const dependencies = data?.dependencies ?? [];
  const bindings = data?.bindings ?? [];

  const servicesById = useMemo(
    () => Object.fromEntries(services.map((service) => [service.id, service])),
    [services],
  );
  const connectionsById = useMemo(
    () => Object.fromEntries(connections.map((connection) => [connection.id, connection])),
    [connections],
  );

  const serviceDelete = useMutation({
    mutationFn: deleteService,
    onSuccess: () => {
      toast.success("Service deleted");
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
  const connectionDelete = useMutation({
    mutationFn: deleteConnection,
    onSuccess: () => {
      toast.success("Connection deleted");
      invalidateTopology(queryClient, project.id);
    },
  });

  if (isLoading) {
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-48 rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <Card size="sm">
          <CardHeader>
            <CardTitle>Services</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{services.length}</CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle>Connections</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{connections.length}</CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle>Dependencies</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{dependencies.length}</CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle>Bindings</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{bindings.length}</CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <Plug className="h-4 w-4" />
                Services
              </CardTitle>
              <CreateServiceButton projectId={project.id} />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {services.length ? (
              services.map((service) => (
                <ServiceCard
                  key={service.id}
                  service={service}
                  onDelete={(id) => serviceDelete.mutate(id)}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No services yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <Plug className="h-4 w-4" />
                Connections
              </CardTitle>
              <CreateConnectionDialog projectId={project.id} />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {connections.length ? (
              connections.map((connection) => (
                <ConnectionCard
                  key={connection.id}
                  connection={connection}
                  onDelete={(id) => connectionDelete.mutate(id)}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No connections yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <Workflow className="h-4 w-4" />
                Service Dependencies
              </CardTitle>
              <CreateDependencyButton projectId={project.id} services={services} />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {dependencies.length ? (
              dependencies.map((dependency) => (
                <DependencyRow
                  key={dependency.id}
                  dependency={dependency}
                  servicesById={servicesById}
                  onDelete={(id) => dependencyDelete.mutate(id)}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No dependencies yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2">
                <Link2 className="h-4 w-4" />
                Service Bindings
              </CardTitle>
              <CreateBindingButton
                projectId={project.id}
                services={services}
                connections={connections}
              />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {bindings.length ? (
              bindings.map((binding) => (
                <BindingRow
                  key={binding.id}
                  binding={binding}
                  servicesById={servicesById}
                  connectionsById={connectionsById}
                  onDelete={(id) => bindingDelete.mutate(id)}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No bindings yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
