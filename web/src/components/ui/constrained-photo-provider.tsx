import { type ComponentProps } from "react";
import { PhotoProvider } from "react-photo-view";
import { cn } from "@/lib/utils";

type ConstrainedPhotoProviderProps = ComponentProps<typeof PhotoProvider>;

export function ConstrainedPhotoProvider({
  className,
  maskClassName,
  photoClassName,
  ...props
}: ConstrainedPhotoProviderProps) {
  return (
    <PhotoProvider
      {...props}
      maskOpacity={0}
      className={cn("chronos-photo-preview", className)}
      maskClassName={cn("chronos-photo-preview__mask", maskClassName)}
      photoClassName={cn("chronos-photo-preview__photo", photoClassName)}
    />
  );
}
