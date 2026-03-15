import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { createInfrastructure } from "@/api/infrastructures";
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

export function CreateInfrastructureDialog() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("22");
  const [username, setUsername] = useState("root");
  const [password, setPassword] = useState("");
  const queryClient = useQueryClient();

  const resetForm = () => {
    setName("");
    setHost("");
    setPort("22");
    setUsername("root");
    setPassword("");
  };

  const mutation = useMutation({
    mutationFn: () =>
      createInfrastructure({
        name,
        host,
        port: parseInt(port),
        username,
        password: password || undefined,
      }),
    onSuccess: () => {
      toast.success("Infrastructure added");
      queryClient.invalidateQueries({ queryKey: ["infrastructures"] });
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
      <DialogTrigger render={<Button size="sm" />}>
        Add Infrastructure
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Infrastructure</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel>Name</FieldLabel>
            <Input
              placeholder="e.g. Production Server"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <div className="flex gap-3">
            <Field className="flex-1">
              <FieldLabel>Host</FieldLabel>
              <Input
                placeholder="e.g. 192.168.1.1"
                value={host}
                onChange={(e) => setHost(e.target.value)}
              />
            </Field>
            <Field className="w-24">
              <FieldLabel>Port</FieldLabel>
              <Input
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value)}
              />
            </Field>
          </div>
          <Field>
            <FieldLabel>Username</FieldLabel>
            <Input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Password</FieldLabel>
            <Input
              type="password"
              placeholder="Optional"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            Cancel
          </DialogClose>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!name || !host || mutation.isPending}
          >
            {mutation.isPending ? "Adding..." : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
