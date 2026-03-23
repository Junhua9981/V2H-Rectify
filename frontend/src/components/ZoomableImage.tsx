/**
 * ZoomableImage — scroll to zoom (cursor-centred), drag to pan.
 *
 * Fixes:
 *  - wheel listener registered with { passive: false } so e.preventDefault()
 *    actually blocks page scroll.
 *  - pan offset is clamped so the image can never leave the viewport entirely.
 */

import { useRef, useState, useCallback, useEffect } from "react";

interface Props {
  src: string;
  alt: string;
  className?: string;
}

const MIN_SCALE = 0.25;
const MAX_SCALE = 10;
const ZOOM_FACTOR = 1.18;

interface View { scale: number; x: number; y: number }

export default function ZoomableImage({ src, alt, className = "" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // viewRef mirrors state so event handlers always see the latest value
  // without needing to re-subscribe (avoids stale-closure problems).
  const viewRef = useRef<View>({ scale: 1, x: 0, y: 0 });
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });

  const commit = useCallback((next: View) => {
    viewRef.current = next;
    setView(next);
  }, []);

  const reset = useCallback(() => commit({ scale: 1, x: 0, y: 0 }), [commit]);

  /** Clamp pan so the image always overlaps the container by at least 60 px. */
  const clamp = useCallback((x: number, y: number, s: number) => {
    const el = containerRef.current;
    if (!el) return { x, y };
    const { width: cw, height: ch } = el.getBoundingClientRect();
    const overlap = 60;
    const maxX = cw  * s / 2 + cw  / 2 - overlap;
    const maxY = ch * s / 2 + ch / 2 - overlap;
    return {
      x: Math.max(-maxX, Math.min(maxX, x)),
      y: Math.max(-maxY, Math.min(maxY, y)),
    };
  }, []);

  // ── Non-passive wheel → zoom toward cursor, no page scroll ─────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const cx = e.clientX - rect.left - rect.width / 2;
      const cy = e.clientY - rect.top - rect.height / 2;
      const factor = e.deltaY < 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR;
      const v = viewRef.current;
      const ns = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor));
      const rawX = cx - (cx - v.x) * (ns / v.scale);
      const rawY = cy - (cy - v.y) * (ns / v.scale);
      const { x, y } = clamp(rawX, rawY, ns);
      commit({ scale: ns, x, y });
    };

    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, [clamp, commit]);

  // ── Mouse drag ───────────────────────────────────────────────────────────
  const dragStart = useRef<{ mx: number; my: number; ox: number; oy: number } | null>(null);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const v = viewRef.current;
    dragStart.current = { mx: e.clientX, my: e.clientY, ox: v.x, oy: v.y };
    e.preventDefault();
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragStart.current) return;
    const dx = e.clientX - dragStart.current.mx;
    const dy = e.clientY - dragStart.current.my;
    const v = viewRef.current;
    const { x, y } = clamp(dragStart.current.ox + dx, dragStart.current.oy + dy, v.scale);
    commit({ ...v, x, y });
  }, [clamp, commit]);

  const onMouseUp = useCallback(() => { dragStart.current = null; }, []);

  // ── Touch drag ───────────────────────────────────────────────────────────
  const touchRef = useRef<{ x: number; y: number } | null>(null);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 1)
      touchRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!touchRef.current || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - touchRef.current.x;
    const dy = e.touches[0].clientY - touchRef.current.y;
    touchRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    const v = viewRef.current;
    const { x, y } = clamp(v.x + dx, v.y + dy, v.scale);
    commit({ ...v, x, y });
  }, [clamp, commit]);

  const onTouchEnd = useCallback(() => { touchRef.current = null; }, []);

  return (
    <div
      ref={containerRef}
      className={`relative select-none overflow-hidden rounded-xl border border-gray-100 bg-gray-50 cursor-grab active:cursor-grabbing ${className}`}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
    >
      <img
        src={src}
        alt={alt}
        draggable={false}
        className="pointer-events-none block h-full w-full object-contain"
        style={{
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
          transformOrigin: "center center",
        }}
      />

      {/* ── Zoom controls ── */}
      <div className="absolute bottom-3 right-3 flex items-center gap-1.5">
        <span className="rounded-md bg-black/40 px-1.5 py-0.5 text-xs text-white backdrop-blur-sm">
          {Math.round(view.scale * 100)}%
        </span>

        {/* Zoom in */}
        <button
          onClick={() => { const v = viewRef.current; const ns = Math.min(MAX_SCALE, v.scale * ZOOM_FACTOR); commit({ ...v, scale: ns }); }}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-gray-200 bg-white/90 text-sm font-bold text-gray-600 shadow-sm backdrop-blur-sm hover:bg-gray-50 active:scale-95"
          title="放大"
        >+</button>

        {/* Zoom out */}
        <button
          onClick={() => { const v = viewRef.current; const ns = Math.max(MIN_SCALE, v.scale / ZOOM_FACTOR); commit({ ...v, scale: ns }); }}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-gray-200 bg-white/90 text-sm font-bold text-gray-600 shadow-sm backdrop-blur-sm hover:bg-gray-50 active:scale-95"
          title="縮小"
        >−</button>

        {/* Reset */}
        <button
          onClick={reset}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-gray-200 bg-white/90 text-base text-gray-600 shadow-sm backdrop-blur-sm hover:bg-gray-50 active:scale-95"
          title="重置"
        >↺</button>
      </div>
    </div>
  );
}
