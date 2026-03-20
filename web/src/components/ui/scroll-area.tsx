import { useRef } from "react"
import { ScrollArea as ScrollAreaPrimitive } from "@base-ui/react/scroll-area"
import { ArrowUp } from "lucide-react"

import { cn } from "@/lib/utils"

function ScrollToTopButton({
  viewportRef,
}: {
  viewportRef: React.RefObject<HTMLDivElement | null>
}) {
  return (
    <button
      type="button"
      className="absolute bottom-4 right-4 z-10 rounded-full border bg-background p-2 shadow-md
        transition-all duration-200 opacity-0 scale-90 pointer-events-none hover:bg-accent
        group-data-[overflow-y-start]/scroll:opacity-100
        group-data-[overflow-y-start]/scroll:scale-100
        group-data-[overflow-y-start]/scroll:pointer-events-auto"
      onClick={() =>
        viewportRef.current?.scrollTo({ top: 0, behavior: "smooth" })
      }
    >
      <ArrowUp className="h-4 w-4" />
    </button>
  )
}

function ScrollArea({
  className,
  children,
  scrollToTop,
  ...props
}: ScrollAreaPrimitive.Root.Props & { scrollToTop?: boolean }) {
  const viewportRef = useRef<HTMLDivElement>(null)

  return (
    <ScrollAreaPrimitive.Root
      data-slot="scroll-area"
      className={cn("relative", scrollToTop && "group/scroll", className)}
      {...(scrollToTop
        ? { overflowEdgeThreshold: { yStart: 100 } }
        : undefined)}
      {...props}
    >
      <ScrollAreaPrimitive.Viewport
        ref={scrollToTop ? viewportRef : undefined}
        data-slot="scroll-area-viewport"
        className="size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1"
      >
        {children}
      </ScrollAreaPrimitive.Viewport>
      <ScrollBar />
      <ScrollAreaPrimitive.Corner />
      {scrollToTop && <ScrollToTopButton viewportRef={viewportRef} />}
    </ScrollAreaPrimitive.Root>
  )
}

function ScrollBar({
  className,
  orientation = "vertical",
  ...props
}: ScrollAreaPrimitive.Scrollbar.Props) {
  return (
    <ScrollAreaPrimitive.Scrollbar
      data-slot="scroll-area-scrollbar"
      data-orientation={orientation}
      orientation={orientation}
      className={cn(
        "flex touch-none p-px transition-colors select-none data-horizontal:h-2.5 data-horizontal:flex-col data-horizontal:border-t data-horizontal:border-t-transparent data-vertical:h-full data-vertical:w-2.5 data-vertical:border-l data-vertical:border-l-transparent",
        className
      )}
      {...props}
    >
      <ScrollAreaPrimitive.Thumb
        data-slot="scroll-area-thumb"
        className="relative flex-1 rounded-full bg-border"
      />
    </ScrollAreaPrimitive.Scrollbar>
  )
}

export { ScrollArea, ScrollBar }
