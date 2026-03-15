import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { createIncident } from "@/api/incidents";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Field, FieldLabel } from "@/components/ui/field";

export function CreateIncidentDialog() {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("medium");
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setSeverity("medium");
  };

  const mutation = useMutation({
    mutationFn: () => createIncident({ title, description, severity }),
    onSuccess: (incident) => {
      toast.success("Incident created");
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setOpen(false);
      navigate({
        to: "/incidents/$incidentId",
        params: { incidentId: incident.id },
      });
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
      <DialogTrigger render={<Button size="sm" data-testid="create-incident-btn" />}>New Incident</DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Incident</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel>Title</FieldLabel>
            <Input
              placeholder="Incident title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="incident-title"
            />
          </Field>
          <Field>
            <FieldLabel>Description</FieldLabel>
            <Textarea
              placeholder="Describe the incident..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              data-testid="incident-description"
            />
          </Field>
          <Field>
            <FieldLabel>Severity</FieldLabel>
            <Select value={severity} onValueChange={(v) => v && setSeverity(v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            Cancel
          </DialogClose>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!title || !description || mutation.isPending}
            data-testid="submit-incident"
          >
            {mutation.isPending ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
