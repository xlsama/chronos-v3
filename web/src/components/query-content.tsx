import { type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { contentFadeVariants, contentFadeTransition } from "@/lib/motion";

interface QueryContentProps<T> {
  isLoading: boolean;
  data: T | undefined;
  isEmpty?: (data: T) => boolean;
  skeleton: ReactNode;
  empty: ReactNode;
  children: (data: T) => ReactNode;
  className?: string;
}

export function QueryContent<T>({
  isLoading,
  data,
  isEmpty,
  skeleton,
  empty,
  children,
  className,
}: QueryContentProps<T>) {
  const showSkeleton = isLoading && data === undefined;
  const showEmpty = !showSkeleton && data !== undefined && (isEmpty ? isEmpty(data) : !data);
  const showContent = !showSkeleton && !showEmpty && data !== undefined;

  return (
    <AnimatePresence mode="wait">
      {showSkeleton && (
        <motion.div
          key="skeleton"
          className={className}
          variants={contentFadeVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={contentFadeTransition}
        >
          {skeleton}
        </motion.div>
      )}
      {showEmpty && (
        <motion.div
          key="empty"
          className={className}
          variants={contentFadeVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={contentFadeTransition}
        >
          {empty}
        </motion.div>
      )}
      {showContent && (
        <motion.div
          key="content"
          className={className}
          variants={contentFadeVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={contentFadeTransition}
        >
          {children(data)}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
