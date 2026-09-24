import { useCallback, useState } from "react";
import type { MouseEvent } from "react";

export interface TooltipState {
  text: string;
  x: number;
  y: number;
}

/**
 * Floating dark tooltip used across the dashboards (identical positioning
 * rules to the legacy `showTooltip/moveTooltip/hideTooltip` helpers).
 */
export function useTooltip() {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const computePosition = useCallback((e: MouseEvent) => {
    let x = e.clientX + 15;
    let y = e.clientY + 15;
    if (x + 250 > window.innerWidth) x = e.clientX - 260;
    if (y + 100 > window.innerHeight) y = e.clientY - 120;
    return { x, y };
  }, []);

  const showTooltip = useCallback(
    (e: MouseEvent, text: string) => {
      setTooltip({ text, ...computePosition(e) });
    },
    [computePosition],
  );

  const moveTooltip = useCallback(
    (e: MouseEvent) => {
      setTooltip((prev) => (prev ? { ...prev, ...computePosition(e) } : prev));
    },
    [computePosition],
  );

  const hideTooltip = useCallback(() => setTooltip(null), []);

  return { tooltip, showTooltip, moveTooltip, hideTooltip };
}
