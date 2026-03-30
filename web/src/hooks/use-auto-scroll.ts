import { useRef, useState, useEffect, useCallback } from "react";

interface UseAutoScrollOptions {
  enabled?: boolean;
  threshold?: number;
  smooth?: boolean;
}

interface UseAutoScrollReturn {
  scrollRef: (node: HTMLDivElement | null) => void;
  bottomRef: React.RefObject<HTMLDivElement | null>;
  isAtBottom: boolean;
  scrollToBottom: () => void;
  scrollElement: HTMLDivElement | null;
}

export function useAutoScroll(
  options: UseAutoScrollOptions = {},
): UseAutoScrollReturn {
  const { enabled = true, threshold = 100, smooth = false } = options;

  const scrollElRef = useRef<HTMLDivElement | null>(null);
  const [scrollEl, setScrollEl] = useState<HTMLDivElement | null>(null);
  const scrollRef = useCallback(
    (node: HTMLDivElement | null) => { scrollElRef.current = node; setScrollEl(node); },
    [],
  );
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const scrollRafId = useRef(0);
  const mutationTimerId = useRef<ReturnType<typeof setTimeout>>(undefined);
  const resizeRafId = useRef(0);

  // scroll 事件：rAF 节流，检测用户是否在底部
  useEffect(() => {
    if (!scrollEl) return;

    const onScroll = () => {
      if (scrollRafId.current) return;
      scrollRafId.current = requestAnimationFrame(() => {
        scrollRafId.current = 0;
        const atBottom =
          scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight <
          threshold;
        shouldAutoScroll.current = atBottom;
        setIsAtBottom(atBottom);
      });
    };

    scrollEl.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      scrollEl.removeEventListener("scroll", onScroll);
      if (scrollRafId.current) cancelAnimationFrame(scrollRafId.current);
    };
  }, [scrollEl, threshold]);

  // MutationObserver：监听 DOM 子节点变化，自动滚动到底部
  // 只监听 childList（新增/删除节点），不监听 characterData（逐字更新会触发过于频繁）
  // 使用 200ms throttle 批量合并快速连续的 DOM 变化，配合 smooth scroll 消除闪烁
  useEffect(() => {
    if (!scrollEl || !enabled) return;

    const doScroll = () => {
      if (shouldAutoScroll.current) {
        scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: "smooth" });
      }
    };

    const observer = new MutationObserver(() => {
      if (mutationTimerId.current) return;
      mutationTimerId.current = setTimeout(() => {
        mutationTimerId.current = undefined;
        doScroll();
      }, 200);
    });

    observer.observe(scrollEl, {
      childList: true,
      subtree: true,
    });

    // 初始滚动到底部
    if (scrollElRef.current) scrollElRef.current.scrollTop = scrollElRef.current.scrollHeight;

    return () => {
      observer.disconnect();
      if (mutationTimerId.current) clearTimeout(mutationTimerId.current);
    };
  }, [scrollEl, enabled, threshold]);

  // ResizeObserver：当容器自身高度变化时，也保持底部对齐。
  // 这能覆盖 header/sources 行插入后，可视区缩小但子树内容本身未变的情况。
  useEffect(() => {
    if (!scrollEl || !enabled) return;

    const observer = new ResizeObserver(() => {
      if (resizeRafId.current) return;
      resizeRafId.current = requestAnimationFrame(() => {
        resizeRafId.current = 0;
        if (shouldAutoScroll.current) {
          scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: "smooth" });
        }
      });
    });

    observer.observe(scrollEl);

    return () => {
      observer.disconnect();
      if (resizeRafId.current) cancelAnimationFrame(resizeRafId.current);
    };
  }, [scrollEl, enabled, threshold]);

  const scrollToBottom = useCallback(() => {
    shouldAutoScroll.current = true;
    setIsAtBottom(true);
    if (scrollElRef.current) {
      scrollElRef.current.scrollTo({
        top: scrollElRef.current.scrollHeight,
        behavior: smooth ? "smooth" : "instant",
      });
    }
  }, [smooth]);

  return { scrollRef, bottomRef, isAtBottom, scrollToBottom, scrollElement: scrollEl };
}
