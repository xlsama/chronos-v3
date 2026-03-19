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
}

export function useAutoScroll(
  options: UseAutoScrollOptions = {},
): UseAutoScrollReturn {
  const { enabled = true, threshold = 100, smooth = false } = options;

  const [scrollEl, setScrollEl] = useState<HTMLDivElement | null>(null);
  const scrollRef = useCallback(
    (node: HTMLDivElement | null) => setScrollEl(node),
    [],
  );
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const scrollRafId = useRef(0);
  const mutationRafId = useRef(0);

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

  // MutationObserver：监听深层 DOM 变化，自动滚动到底部
  useEffect(() => {
    if (!scrollEl || !enabled) return;

    const observer = new MutationObserver(() => {
      if (!shouldAutoScroll.current) return;
      if (mutationRafId.current) return;
      mutationRafId.current = requestAnimationFrame(() => {
        mutationRafId.current = 0;
        if (shouldAutoScroll.current) {
          scrollEl.scrollTop = scrollEl.scrollHeight;
        }
      });
    });

    observer.observe(scrollEl, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["style"],
    });

    // 初始滚动到底部
    scrollEl.scrollTop = scrollEl.scrollHeight;

    return () => {
      observer.disconnect();
      if (mutationRafId.current) cancelAnimationFrame(mutationRafId.current);
    };
  }, [scrollEl, enabled]);

  const scrollToBottom = useCallback(() => {
    shouldAutoScroll.current = true;
    setIsAtBottom(true);
    if (smooth) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    } else if (scrollEl) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  }, [smooth, scrollEl]);

  return { scrollRef, bottomRef, isAtBottom, scrollToBottom };
}
