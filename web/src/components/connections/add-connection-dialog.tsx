import { useState } from "react";
import { Cable, Database, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ServerForm } from "@/components/servers/create-server-dialog";
import { ServiceForm } from "./service-form";

type Step = "server" | "service" | null;

export function AddConnectionDialog() {
  const [step, setStep] = useState<Step>(null);

  const handleClose = () => {
    setStep(null);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger openOnHover delay={0} render={<Button size="sm" />}>
          <Cable className="mr-1 h-4 w-4" />
          添加连接
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuItem
            className="flex items-start gap-3 p-3"
            onClick={() => setStep("service")}
          >
            <Database className="mt-1 h-5 w-5 shrink-0 text-muted-foreground" />
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">添加服务</span>
              <span className="text-xs text-muted-foreground">
                MySQL, Redis, Prometheus 等
              </span>
            </div>
          </DropdownMenuItem>
          <DropdownMenuItem
            className="flex items-start gap-3 p-3"
            onClick={() => setStep("server")}
          >
            <Server className="mt-1 h-5 w-5 shrink-0 text-muted-foreground" />
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">添加服务器</span>
              <span className="text-xs text-muted-foreground">
                通过 SSH 连接远程服务器
              </span>
            </div>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={step !== null} onOpenChange={(v) => !v && handleClose()}>
        <DialogContent className="sm:max-w-lg">
          {step === "server" && (
            <>
              <DialogHeader>
                <DialogTitle>添加服务器</DialogTitle>
              </DialogHeader>
              <ServerForm mode="create" onSuccess={handleClose} />
            </>
          )}
          {step === "service" && (
            <>
              <DialogHeader>
                <DialogTitle>添加服务</DialogTitle>
              </DialogHeader>
              <ServiceForm mode="create" onSuccess={handleClose} />
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
