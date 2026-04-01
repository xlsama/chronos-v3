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
  const contentResizeRafId = useRef(0);

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
        scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: smooth ? "smooth" : "instant" });
      }
    };

    const observer = new MutationObserver(() => {
      // trailing-edge debounce：每次 mutation 重置计时器，等 DOM 变化停歇后再滚动
      if (mutationTimerId.current) clearTimeout(mutationTimerId.current);
      mutationTimerId.current = setTimeout(() => {
        mutationTimerId.current = undefined;
        doScroll();
        // DOM 变化后重新检测是否在底部（覆盖折叠/展开导致内容高度变化的场景）
        // 只更新 UI 状态，不动 shouldAutoScroll（它只由用户滚动行为控制）
        const atBottom =
          scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight <
          threshold;
        setIsAtBottom(atBottom);
      }, 150);
    });

    observer.observe(scrollEl, {
      childList: true,
      subtree: true,
    });

    // 初始滚动：rAF 延迟到当前渲染完成后，instant 跳转避免动画期间 scrollHeight 变化
    const rafId = requestAnimationFrame(() => {
      if (scrollElRef.current) {
        scrollElRef.current.scrollTo({ top: scrollElRef.current.scrollHeight, behavior: "instant" });
      }
    });

    return () => {
      observer.disconnect();
      cancelAnimationFrame(rafId);
      if (mutationTimerId.current) clearTimeout(mutationTimerId.current);
    };
  }, [scrollEl, enabled, smooth, threshold]);

  // ResizeObserver：当容器自身高度变化时，也保持底部对齐。
  // 这能覆盖 header/sources 行插入后，可视区缩小但子树内容本身未变的情况。
  useEffect(() => {
    if (!scrollEl || !enabled) return;

    const observer = new ResizeObserver(() => {
      if (resizeRafId.current) return;
      resizeRafId.current = requestAnimationFrame(() => {
        resizeRafId.current = 0;
        if (shouldAutoScroll.current) {
          scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: smooth ? "smooth" : "instant" });
        }
      });
    });

    observer.observe(scrollEl);

    return () => {
      observer.disconnect();
      if (resizeRafId.current) cancelAnimationFrame(resizeRafId.current);
    };
  }, [scrollEl, enabled, smooth, threshold]);

  // ResizeObserver on content children：检测内容高度变化（覆盖 CSS 动画、Virtuoso 懒渲染等场景）
  // MutationObserver 只能捕获 DOM 节点增删，无法捕获 framer-motion 的 height 动画（纯 style 变化）
  // 通过监听滚动容器子元素的 resize，能在动画过程中实时更新 isAtBottom
  useEffect(() => {
    if (!scrollEl) return;

    const ro = new ResizeObserver(() => {
      if (contentResizeRafId.current) cancelAnimationFrame(contentResizeRafId.current);
      contentResizeRafId.current = requestAnimationFrame(() => {
        contentResizeRafId.current = 0;
        const atBottom =
          scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight <
          threshold;
        setIsAtBottom(atBottom);
      });
    });

    for (const child of Array.from(scrollEl.children)) {
      ro.observe(child);
    }

    return () => {
      ro.disconnect();
      if (contentResizeRafId.current) cancelAnimationFrame(contentResizeRafId.current);
    };
  }, [scrollEl, threshold]);

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
