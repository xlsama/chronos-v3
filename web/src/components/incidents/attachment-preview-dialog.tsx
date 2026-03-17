import { useEffect, useState } from "react";
import type { Attachment } from "@/lib/types";
import { getAttachmentUrl } from "@/api/attachments";
import { getFileTypeFromContentType } from "@/lib/file-utils";
import { FilePreview } from "@/components/ui/file-preview";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface AttachmentPreviewDialogProps {
  attachment: Attachment | null;
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
  const needsFetch = fileType !== "image" && fileType !== "pdf";

  useEffect(() => {
    if (!open || !attachment || !needsFetch) {
      setTextContent("");
      return;
    }
    setLoading(true);
    fetch(fileUrl)
      .then((res) => res.text())
      .then((text) => setTextContent(text))
      .catch(() => setTextContent("加载失败"))
      .finally(() => setLoading(false));
  }, [open, attachment?.id, needsFetch, fileUrl]);

  if (!attachment) return null;

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
