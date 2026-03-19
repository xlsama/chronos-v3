import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { VersionHistoryContent } from "./version-history-content";

interface VersionHistoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityType: string;
  entityId: string;
  title: string;
}

export function VersionHistoryDialog({
  open,
  onOpenChange,
  entityType,
  entityId,
  title,
}: VersionHistoryDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[90vh] flex-col sm:max-w-[90vw]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="sr-only">
            查看版本变更历史和内容差异
          </DialogDescription>
        </DialogHeader>
        <VersionHistoryContent entityType={entityType} entityId={entityId} />
      </DialogContent>
    </Dialog>
  );
}
