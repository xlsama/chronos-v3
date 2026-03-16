import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { createService } from "@/api/services";
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
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const serviceTypes = [
  { value: "process", label: "Process" },
  { value: "docker", label: "Docker" },
  { value: "systemd", label: "Systemd" },
  { value: "database", label: "Database" },
  { value: "cache", label: "Cache" },
  { value: "queue", label: "Queue" },
  { value: "cron_job", label: "Cron Job" },
  { value: "k8s_deployment", label: "K8s Deployment" },
  { value: "k8s_statefulset", label: "K8s StatefulSet" },
  { value: "k8s_service", label: "K8s Service" },
];

export function CreateServiceDialog({ infraId }: { infraId: string }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [serviceType, setServiceType] = useState("process");
  const [port, setPort] = useState("");
  const [namespace, setNamespace] = useState("");
  const queryClient = useQueryClient();

  const resetForm = () => {
    setName("");
    setServiceType("process");
    setPort("");
    setNamespace("");
  };

  const mutation = useMutation({
    mutationFn: () =>
      createService({
        infrastructure_id: infraId,
        name,
        service_type: serviceType,
        port: port ? parseInt(port) : undefined,
        namespace: namespace || undefined,
      }),
    onSuccess: () => {
      toast.success("Service added");
      queryClient.invalidateQueries({ queryKey: ["services", infraId] });
      setOpen(false);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(open) => {
        setOpen(open);
        if (!open) resetForm();
      }}
    >
      <DialogTrigger
        render={
          <Button data-testid="add-service-btn" variant="ghost" size="sm" className="h-7 px-2 text-xs" />
        }
      >
        <Plus className="h-3 w-3 mr-1" />
        Add
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Service</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel>Name</FieldLabel>
            <Input
              placeholder="e.g. mysql-main"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Type</FieldLabel>
            <Select value={serviceType} onValueChange={setServiceType}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {serviceTypes.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <div className="flex gap-3">
            <Field className="flex-1">
              <FieldLabel>Port</FieldLabel>
              <Input
                type="number"
                placeholder="Optional"
                value={port}
                onChange={(e) => setPort(e.target.value)}
              />
            </Field>
            <Field className="flex-1">
              <FieldLabel>Namespace</FieldLabel>
              <Input
                placeholder="Optional (K8s)"
                value={namespace}
                onChange={(e) => setNamespace(e.target.value)}
              />
            </Field>
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            Cancel
          </DialogClose>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!name || mutation.isPending}
          >
            {mutation.isPending ? "Adding..." : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
