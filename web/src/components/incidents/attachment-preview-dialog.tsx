import { useEffect, useState } from "react";
import { getAttachmentUrl } from "@/api/attachments";
import { getFileTypeFromContentType } from "@/lib/file-utils";
import { FilePreview } from "@/components/ui/file-preview";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface PreviewableAttachment {
  id: string;
  filename: string;
  content_type: string;
}

interface AttachmentPreviewDialogProps {
  attachment: PreviewableAttachment | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AttachmentPreviewDialog({
  attachment,
  open,
  onOpenChange,
}: AttachmentPreviewDialogProps) {
  const [textContent, setTextContent] = useState("");
  const [loading, setLoading] = useState(false);

  const fileType = attachment
    ? getFileTypeFromContentType(attachment.content_type, attachment.filename)
    : "text";
  const fileUrl = attachment ? getAttachmentUrl(attachment.id) : "";
  const needsFetch = fileType !== "pdf" && fileType !== "image";

  useEffect(() => {
    if (!open || !attachment || !needsFetch) {
      return;
    }
    let cancelled = false;
    // oxlint-disable-next-line react/set-state-in-effect -- loading indicator for async fetch
    setLoading(true);
    fetch(fileUrl)
      .then((res) => res.text())
      .then((text) => { if (!cancelled) setTextContent(text); })
      .catch(() => { if (!cancelled) setTextContent("加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; setTextContent(""); };
  }, [open, attachment, needsFetch, fileUrl]);

  if (!attachment || !open) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="truncate">{attachment.filename}</DialogTitle>
        </DialogHeader>
        <div className="max-h-[70vh] min-h-[200px] overflow-hidden rounded-md border">
          {loading ? (
            <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
              加载中...
            </div>
          ) : (
            <FilePreview
              content={textContent}
              fileType={fileType}
              fileUrl={fileUrl}
              filename={attachment.filename}
              className="h-[70vh]"
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
