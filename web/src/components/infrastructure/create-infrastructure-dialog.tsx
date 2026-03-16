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
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function CreateInfrastructureDialog() {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState("ssh");
  const [name, setName] = useState("");
  // SSH fields
  const [host, setHost] = useState("");
  const [port, setPort] = useState("22");
  const [username, setUsername] = useState("root");
  const [password, setPassword] = useState("");
  // K8s fields
  const [kubeconfig, setKubeconfig] = useState("");
  const [context, setContext] = useState("");
  const [namespace, setNamespace] = useState("");
  const queryClient = useQueryClient();

  const resetForm = () => {
    setType("ssh");
    setName("");
    setHost("");
    setPort("22");
    setUsername("root");
    setPassword("");
    setKubeconfig("");
    setContext("");
    setNamespace("");
  };

  const mutation = useMutation({
    mutationFn: () =>
      createInfrastructure({
        name,
        type,
        ...(type === "ssh"
          ? {
              host,
              port: parseInt(port),
              username,
              password: password || undefined,
            }
          : {
              kubeconfig: kubeconfig || undefined,
              context: context || undefined,
              namespace: namespace || undefined,
            }),
      }),
    onSuccess: () => {
      toast.success("Infrastructure added");
      queryClient.invalidateQueries({ queryKey: ["infrastructures"] });
      setOpen(false);
    },
  });

  const isValid =
    name &&
    (type === "ssh" ? host : kubeconfig);

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
            <FieldLabel>Type</FieldLabel>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ssh">SSH Server</SelectItem>
                <SelectItem value="kubernetes">Kubernetes Cluster</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel>Name</FieldLabel>
            <Input
              placeholder={
                type === "ssh"
                  ? "e.g. Production Server"
                  : "e.g. K8s Production"
              }
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>

          {type === "ssh" ? (
            <>
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
            </>
          ) : (
            <>
              <Field>
                <FieldLabel>Kubeconfig</FieldLabel>
                <Textarea
                  placeholder="Paste kubeconfig YAML content here..."
                  rows={6}
                  value={kubeconfig}
                  onChange={(e) => setKubeconfig(e.target.value)}
                />
              </Field>
              <div className="flex gap-3">
                <Field className="flex-1">
                  <FieldLabel>Context</FieldLabel>
                  <Input
                    placeholder="Optional"
                    value={context}
                    onChange={(e) => setContext(e.target.value)}
                  />
                </Field>
                <Field className="flex-1">
                  <FieldLabel>Default Namespace</FieldLabel>
                  <Input
                    placeholder="default"
                    value={namespace}
                    onChange={(e) => setNamespace(e.target.value)}
                  />
                </Field>
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            Cancel
          </DialogClose>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!isValid || mutation.isPending}
          >
            {mutation.isPending ? "Adding..." : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
