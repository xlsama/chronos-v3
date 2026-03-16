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

export function CreateServiceDialog({ connectionId }: { connectionId: string }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createService,
    onSuccess: () => {
      toast.success("Service added");
      queryClient.invalidateQueries({ queryKey: ["services", connectionId] });
      setOpen(false);
    },
  });

  const form = useForm({
    defaultValues: {
      name: "",
      port: "",
      namespace: "",
    },
    onSubmit: ({ value }) => {
      mutation.mutate({
        connection_id: connectionId,
        name: value.name,
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
