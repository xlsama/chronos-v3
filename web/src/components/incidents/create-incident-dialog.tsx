import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import type { Incident } from "@/lib/types";

export function CreateIncidentDialog() {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("medium");
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: () =>
      api<Incident>("/incidents", {
        method: "POST",
        body: { title, description, severity },
      }),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setOpen(false);
      setTitle("");
      setDescription("");
      navigate({ to: "/incidents/$incidentId", params: { incidentId: incident.id } });
    },
  });

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)} size="sm">
        New Incident
      </Button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg space-y-4 rounded-lg bg-background p-6 shadow-lg">
        <h2 className="text-lg font-semibold">Create Incident</h2>
        <div className="space-y-3">
          <input
            type="text"
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
          <textarea
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="w-full rounded-md border px-3 py-2 text-sm"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!title || !description || mutation.isPending}
          >
            {mutation.isPending ? "Creating..." : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}
