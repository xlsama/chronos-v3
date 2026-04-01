import { type ComponentProps } from "react";
import { PhotoProvider } from "react-photo-view";
import { cn } from "@/lib/utils";

type ConstrainedPhotoProviderProps = ComponentProps<typeof PhotoProvider>;

export function ConstrainedPhotoProvider({
  className,
  photoClassName,
  ...props
}: ConstrainedPhotoProviderProps) {
  return (
    <PhotoProvider
      {...props}
      className={cn("chronos-photo-preview", className)}
      photoClassName={cn("chronos-photo-preview__photo", photoClassName)}
    />
  );
}
