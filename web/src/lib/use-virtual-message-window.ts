"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RefObject } from "react";

export interface VirtualMessageItem {
  key: string;
  estimateSize: number;
}

interface VirtualMessageWindowOptions {
  enabled: boolean;
  items: VirtualMessageItem[];
  scrollRef: RefObject<HTMLElement | null>;
  gapPx: number;
  overscanPx?: number;
}

interface VirtualMessageWindow {
  startIndex: number;
  endIndex: number;
  paddingTop: number;
  paddingBottom: number;
  totalSize: number;
  measureItem: (key: string, size: number) => void;
  refreshViewport: () => void;
}

const DEFAULT_OVERSCAN_PX = 900;
const MIN_SIZE_DELTA_PX = 0.5;

export function useVirtualMessageWindow({
  enabled,
  items,
  scrollRef,
  gapPx,
  overscanPx = DEFAULT_OVERSCAN_PX,
}: VirtualMessageWindowOptions): VirtualMessageWindow {
  const [sizes, setSizes] = useState<Map<string, number>>(() => new Map());
  const [viewport, setViewport] = useState({ scrollTop: 0, height: 0 });
  const itemKey = useMemo(() => items.map((item) => item.key).join("\n"), [items]);

  const refreshViewport = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setViewport((current) => {
      const next = { scrollTop: el.scrollTop, height: el.clientHeight };
      return current.scrollTop === next.scrollTop && current.height === next.height
        ? current
        : next;
    });
  }, [scrollRef]);

  useEffect(() => {
    refreshViewport();
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(refreshViewport);
    ro.observe(el);
    return () => ro.disconnect();
  }, [itemKey, refreshViewport, scrollRef]);

  const measureItem = useCallback((key: string, size: number) => {
    if (!Number.isFinite(size) || size <= 0) return;
    setSizes((current) => {
      const previous = current.get(key);
      if (
        previous !== undefined &&
        Math.abs(previous - size) < MIN_SIZE_DELTA_PX
      ) {
        return current;
      }
      const next = new Map(current);
      next.set(key, size);
      return next;
    });
  }, []);

  const layout = useMemo(() => {
    const starts: number[] = [];
    let cursor = 0;
    for (let index = 0; index < items.length; index += 1) {
      starts.push(cursor);
      const item = items[index];
      cursor += sizes.get(item.key) ?? item.estimateSize;
      if (index < items.length - 1) cursor += gapPx;
    }
    return { starts, totalSize: cursor };
  }, [gapPx, items, sizes]);

  const count = items.length;
  if (!enabled || count === 0) {
    return {
      startIndex: 0,
      endIndex: count,
      paddingTop: 0,
      paddingBottom: 0,
      totalSize: layout.totalSize,
      measureItem,
      refreshViewport,
    };
  }

  const visibleTop = Math.max(0, viewport.scrollTop - overscanPx);
  const visibleBottom = viewport.scrollTop + viewport.height + overscanPx;
  let startIndex = 0;
  while (startIndex < count - 1) {
    const item = items[startIndex];
    const itemEnd =
      layout.starts[startIndex] + (sizes.get(item.key) ?? item.estimateSize);
    if (itemEnd >= visibleTop) break;
    startIndex += 1;
  }

  let endIndex = startIndex;
  while (endIndex < count) {
    const itemStart = layout.starts[endIndex] ?? layout.totalSize;
    if (itemStart > visibleBottom && endIndex > startIndex) break;
    endIndex += 1;
  }

  const paddingTop = layout.starts[startIndex] ?? 0;
  const paddingBottom = Math.max(
    0,
    layout.totalSize - (layout.starts[endIndex] ?? layout.totalSize),
  );

  return {
    startIndex,
    endIndex,
    paddingTop,
    paddingBottom,
    totalSize: layout.totalSize,
    measureItem,
    refreshViewport,
  };
}
