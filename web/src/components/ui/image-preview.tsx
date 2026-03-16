import { useState } from "react";
import { ImageOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

interface ImagePreviewProps {
  src: string;
  alt?: string;
  className?: string;
}

export function ImagePreview({ src, alt, className }: ImagePreviewProps) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  if (error) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-2 text-muted-foreground",
          className,
        )}
      >
        <ImageOff className="h-10 w-10" />
        <span className="text-sm">图片加载失败</span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "relative flex items-center justify-center bg-muted/30",
        className,
      )}
    >
      {!loaded && <Skeleton className="absolute inset-4 rounded" />}
      <img
        src={src}
        alt={alt}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        className={cn(
          "max-h-full max-w-full rounded object-contain",
          !loaded && "invisible",
        )}
      />
    </div>
  );
}
