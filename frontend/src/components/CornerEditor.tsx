/**
 * CornerEditor — Konva canvas for interactive corner adjustment.
 *
 * Shows the uploaded image with 4 draggable circles at the detected corners.
 * User can drag to adjust, then confirm to trigger perspective correction.
 */

import { useEffect, useRef, useState } from "react";
import { Stage, Layer, Image as KonvaImage, Circle, Line } from "react-konva";
import type { Point } from "../lib/types";

interface Props {
  imageUrl: string;
  corners: Point[];
  onConfirm: (corners: Point[]) => void;
  onSkip: () => void;
}

const CORNER_RADIUS = 10;
const MAGNIFIER_SIZE = 140;
const MAGNIFIER_ZOOM = 2.4;
const MAGNIFIER_OFFSET = 20;
const MAX_VIEWPORT_HEIGHT_RATIO = 0.82;
const MAX_STAGE_HEIGHT = 980;
const CORNER_COLORS = ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6"]; // TL TR BR BL
const CORNER_LABELS = ["左上", "右上", "右下", "左下"];

export default function CornerEditor({ imageUrl, corners, onConfirm, onSkip }: Props) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [pts, setPts] = useState<Point[]>(corners);
  const containerRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [activeDrag, setActiveDrag] = useState<{ idx: number; x: number; y: number } | null>(null);

  const fitStageToContainer = (image: HTMLImageElement) => {
    const maxW = containerRef.current?.clientWidth ?? 1000;
    const maxH = Math.min(window.innerHeight * MAX_VIEWPORT_HEIGHT_RATIO, MAX_STAGE_HEIGHT);
    const nextScale = Math.min(maxW / image.width, maxH / image.height, 1);
    setScale(nextScale);
    setStageSize({ width: image.width * nextScale, height: image.height * nextScale });
  };

  // Load image
  useEffect(() => {
    const image = new window.Image();
    image.src = imageUrl;
    image.onload = () => {
      setImg(image);
      fitStageToContainer(image);
    };
  }, [imageUrl]);

  useEffect(() => {
    if (!img) return;
    const onResize = () => fitStageToContainer(img);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [img]);

  const handleDrag = (idx: number, x: number, y: number) => {
    setPts((prev) => {
      const next = [...prev];
      next[idx] = { x: x / scale, y: y / scale };
      return next;
    });
  };

  const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

  const magnifierX = activeDrag
    ? clamp(activeDrag.x + MAGNIFIER_OFFSET, 8, stageSize.width - MAGNIFIER_SIZE - 8)
    : 0;
  const magnifierY = activeDrag
    ? clamp(activeDrag.y + MAGNIFIER_OFFSET, 8, stageSize.height - MAGNIFIER_SIZE - 8)
    : 0;

  // Draw a polygon connecting 4 corners
  const flatLine = pts.flatMap((p) => [p.x * scale, p.y * scale]);

  return (
    <div className="rounded-2xl border border-gray-200 bg-white/90 p-4 shadow-sm sm:p-6">
      <p className="mb-4 text-sm text-gray-600">
        拖曳四個角點來對齊稿紙邊緣，或按「跳過」直接辨識
      </p>

      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-xl border border-gray-300 bg-gray-900"
      >
        <Stage width={stageSize.width} height={stageSize.height}>
          <Layer>
            {img && (
              <KonvaImage image={img} width={stageSize.width} height={stageSize.height} />
            )}
            {/* Polygon outline */}
            <Line
              points={[...flatLine, flatLine[0], flatLine[1]]}
              stroke="#6366f1"
              strokeWidth={2}
              dash={[6, 4]}
              closed
            />
            {/* Draggable corner circles */}
            {pts.map((p, i) => (
              <Circle
                key={i}
                x={p.x * scale}
                y={p.y * scale}
                radius={CORNER_RADIUS}
                fill={CORNER_COLORS[i]}
                stroke="white"
                strokeWidth={2}
                draggable
                onDragStart={(e) => {
                  setActiveDrag({ idx: i, x: e.target.x(), y: e.target.y() });
                }}
                onDragMove={(e) => {
                  const nextX = e.target.x();
                  const nextY = e.target.y();
                  handleDrag(i, nextX, nextY);
                  setActiveDrag({ idx: i, x: nextX, y: nextY });
                }}
                onDragEnd={() => setActiveDrag(null)}
                shadowColor="black"
                shadowBlur={4}
                shadowOpacity={0.3}
              />
            ))}
          </Layer>
        </Stage>

        {img && activeDrag && (
          <div
            className="pointer-events-none absolute overflow-hidden rounded-xl border-2 border-white bg-gray-950/90 shadow-lg"
            style={{
              width: MAGNIFIER_SIZE,
              height: MAGNIFIER_SIZE,
              left: magnifierX,
              top: magnifierY,
              backgroundImage: `url(${imageUrl})`,
              backgroundRepeat: "no-repeat",
              backgroundSize: `${img.width * MAGNIFIER_ZOOM}px ${img.height * MAGNIFIER_ZOOM}px`,
              backgroundPosition: `${-(activeDrag.x / scale) * MAGNIFIER_ZOOM + MAGNIFIER_SIZE / 2}px ${-(activeDrag.y / scale) * MAGNIFIER_ZOOM + MAGNIFIER_SIZE / 2}px`,
            }}
          >
            <div
              className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-white"
              style={{ mixBlendMode: "difference" }}
              aria-hidden="true"
            />
            <div
              className="absolute left-0 top-1/2 h-px w-full -translate-y-1/2 bg-white"
              style={{ mixBlendMode: "difference" }}
              aria-hidden="true"
            />
            <div className="absolute right-2 top-2 rounded bg-black/45 px-1.5 py-0.5 text-[10px] font-medium text-white">
              {CORNER_LABELS[activeDrag.idx]}
            </div>
          </div>
        )}
      </div>

      {/* Corner labels legend */}
      <div className="mt-4 flex flex-wrap gap-3 text-xs text-gray-600">
        {CORNER_LABELS.map((l, i) => (
          <span key={i} className="flex items-center gap-1 rounded-full bg-gray-100 px-2 py-1">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ backgroundColor: CORNER_COLORS[i] }}
            />
            {l}
          </span>
        ))}
      </div>

      {/* Actions */}
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          onClick={() => onConfirm(pts)}
          className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
        >
          確認校正
        </button>
        <button
          onClick={onSkip}
          className="rounded-lg border border-gray-300 bg-white px-5 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
        >
          跳過
        </button>
      </div>
    </div>
  );
}
