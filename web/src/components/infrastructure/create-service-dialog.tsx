import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "@tanstack/react-form";
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
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const serviceTypes = [
  { value: "mysql", label: "MySQL" },
  { value: "postgresql", label: "PostgreSQL" },
  { value: "redis", label: "Redis" },
  { value: "mongodb", label: "MongoDB" },
  { value: "elasticsearch", label: "Elasticsearch" },
  { value: "nginx", label: "Nginx" },
  { value: "apache", label: "Apache" },
  { value: "cron_job", label: "Cron Job" },
  { value: "systemd", label: "Systemd" },
  { value: "docker_container", label: "Docker Container" },
  { value: "k8s_deployment", label: "K8s Deployment" },
  { value: "k8s_statefulset", label: "K8s StatefulSet" },
  { value: "java_app", label: "Java App" },
  { value: "node_app", label: "Node.js App" },
  { value: "python_app", label: "Python App" },
  { value: "custom", label: "Custom" },
];

export function CreateServiceDialog({ infraId }: { infraId: string }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createService,
    onSuccess: () => {
      toast.success("Service added");
      queryClient.invalidateQueries({ queryKey: ["services", infraId] });
      setOpen(false);
    },
  });

  const form = useForm({
    defaultValues: {
      name: "",
      service_type: "custom",
      port: "",
      namespace: "",
    },
    onSubmit: ({ value }) => {
      mutation.mutate({
        infrastructure_id: infraId,
        name: value.name,
        service_type: value.service_type,
        port: value.port ? Number(value.port) : undefined,
        namespace: value.namespace || undefined,
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
      <DialogTrigger
        render={
          <Button
            data-testid="add-service-btn"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
          />
        }
      >
        <Plus className="h-3 w-3 mr-1" />
        Add
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Service</DialogTitle>
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
                  <FieldLabel>Name</FieldLabel>
                  <Input
                    placeholder="e.g. mysql-main"
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
            <form.Field name="service_type">
              {(field) => (
                <Field>
                  <FieldLabel>Type</FieldLabel>
                  <Select
                    value={field.state.value}
                    onValueChange={(v) => field.handleChange(v ?? "custom")}
                  >
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
              )}
            </form.Field>
            <div className="flex gap-3">
              <form.Field name="port">
                {(field) => (
                  <Field className="flex-1">
                    <FieldLabel>Port</FieldLabel>
                    <Input
                      type="number"
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
                    <FieldLabel>Namespace</FieldLabel>
                    <Input
                      placeholder="Optional (K8s)"
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                  </Field>
                )}
              </form.Field>
            </div>
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
