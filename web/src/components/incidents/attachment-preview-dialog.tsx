import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
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

function ImageLightbox({
  src,
  filename,
  onClose,
}: {
  src: string;
  filename: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      {/* Top bar */}
      <div
        className="fixed top-0 right-0 left-0 z-10 flex items-center justify-between px-4 py-3"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="truncate text-sm text-white/80">{filename}</span>
        <button
          onClick={onClose}
          className="rounded-full p-1.5 text-white/80 transition-colors hover:bg-white/20 hover:text-white"
        >
          <X className="size-5" />
        </button>
      </div>

      {/* Image */}
      <img
        src={src}
        alt={filename}
        className="max-h-[90vh] max-w-[90vw] object-contain"
        onClick={(e) => e.stopPropagation()}
      />
    </div>,
    document.body,
  );
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
  const isImage = fileType === "image";
  const needsFetch = !isImage && fileType !== "pdf";

  const handleClose = useCallback(() => onOpenChange(false), [onOpenChange]);

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

  if (!attachment || !open) return null;

  // Image → lightbox overlay
  if (isImage) {
    return (
      <ImageLightbox
        src={fileUrl}
        filename={attachment.filename}
        onClose={handleClose}
      />
    );
  }

  // Non-image → Dialog
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
