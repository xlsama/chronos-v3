import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { discoverServices } from "@/api/services";
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

export function DiscoverServicesDialog({ infraId }: { infraId: string }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => discoverServices(infraId),
    onSuccess: (data) => {
      toast.success(`Discovered ${data.discovered} services`);
      queryClient.invalidateQueries({ queryKey: ["services", infraId] });
      setOpen(false);
    },
    onError: () => {
      toast.error("Discovery failed");
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button data-testid="discover-services-btn" variant="ghost" size="sm" className="h-7 px-2 text-xs" />
        }
      >
        <Search className="h-3 w-3 mr-1" />
        Discover
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Auto-discover Services</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          This will scan the infrastructure for running services (Docker
          containers, systemd units, listening ports, cron jobs, K8s workloads)
          and add them automatically.
        </p>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            Cancel
          </DialogClose>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Scanning..." : "Start Discovery"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
