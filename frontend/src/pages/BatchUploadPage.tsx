/**
 * BatchUploadPage — upload multiple images for batch OCR.
 *
 * Flow:
 *   1. "upload"  — multi-file dropzone → POST /ocr/batch/prepare
 *   2. "review"  — grid of thumbnails with auto-detected corners
 *                  • confidence badge (green ≥0.8, yellow ≥0.4, red <0.4)
 *                  • "調整角點" opens full CornerEditor for that image
 *                  • confirming adjustments updates corners in state (no API call yet)
 *   3. "editing" — full-screen CornerEditor for one selected image
 *   4. "submitting" — POST /ocr/batch/submit with final corners → navigate to result
 */

import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import CornerEditor from "../components/CornerEditor";
import { prepareBatch, submitBatch } from "../lib/api";
import type { BatchPrepareItem, Point } from "../lib/types";

type Step = "upload" | "preparing" | "review" | "editing" | "submitting";

/** Runtime state per image: prepared item + client-side URL + current corners */
interface ImageItem {
  prepared: BatchPrepareItem;
  imageUrl: string;
  corners: Point[];         // current corners (auto or manually overridden)
  overridden: boolean;      // user has manually confirmed corners for this image
}

function confidenceLabel(c: number): { label: string; color: string } {
  if (c >= 0.8) return { label: "高信心", color: "bg-emerald-100 text-emerald-700" };
  if (c >= 0.4) return { label: "中信心", color: "bg-amber-100 text-amber-700" };
  return { label: "低信心 — 建議調整", color: "bg-red-100 text-red-600" };
}

function getErrMsg(e: unknown) {
  return e instanceof Error ? e.message : "操作失敗，請稍後再試";
}

export default function BatchUploadPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("upload");
  const [items, setItems] = useState<ImageItem[]>([]);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [error, setError] = useState("");

  // ── Step 1: drop files ──────────────────────────────────────────────────

  const onDrop = useCallback(async (accepted: File[]) => {
    if (accepted.length === 0) return;
    const capped = accepted.slice(0, 50);
    setError("");
    setStep("preparing");

    try {
      const res = await prepareBatch(capped);
      const built: ImageItem[] = res.items.map((item, i) => ({
        prepared: item,
        imageUrl: URL.createObjectURL(capped[i]),
        corners: item.corners,
        overridden: false,
      }));
      setItems(built);
      setStep("review");
    } catch (e) {
      setError(`角點偵測失敗：${getErrMsg(e)}`);
      setStep("upload");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/*": [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"] },
    disabled: step !== "upload",
  });

  // ── Step 2: editing a single image's corners ────────────────────────────

  const openEditor = (idx: number) => {
    setEditingIdx(idx);
    setStep("editing");
  };

  const handleEditorConfirm = (pts: Point[]) => {
    if (editingIdx === null) return;
    // Only update corners in state — batch/submit will apply the warp from the
    // original image using these final corners. Never call /corner/correct here
    // because batch/submit always warps from the stored original.
    setItems((prev) =>
      prev.map((it, i) =>
        i === editingIdx ? { ...it, corners: pts, overridden: true } : it,
      ),
    );
    setEditingIdx(null);
    setStep("review");
  };

  const handleEditorSkip = () => {
    setEditingIdx(null);
    setStep("review");
  };

  // ── Step 3: submit all ──────────────────────────────────────────────────

  const handleSubmit = async () => {
    setStep("submitting");
    setError("");
    try {
      const corrections = items.map((it) => ({
        task_id: it.prepared.task_id,
        corners: it.corners,
      }));
      const res = await submitBatch({ corrections });

      // Build imageUrl / filename maps for result page
      const imageUrls: Record<string, string> = {};
      const filenames: Record<string, string> = {};
      res.tasks.forEach((t, i) => {
        imageUrls[t.task_id] = items[i]?.imageUrl ?? "";
        filenames[t.task_id] = items[i]?.prepared.filename ?? t.task_id;
      });

      navigate(`/batch/result?batchId=${res.batch_id}`, {
        state: { imageUrls, filenames },
      });
    } catch (e) {
      setError(`提交失敗：${getErrMsg(e)}`);
      setStep("review");
    }
  };

  // ── Reset ───────────────────────────────────────────────────────────────

  const reset = () => {
    items.forEach((it) => URL.revokeObjectURL(it.imageUrl));
    setItems([]);
    setEditingIdx(null);
    setError("");
    setStep("upload");
  };

  // ── Render ──────────────────────────────────────────────────────────────

  const editingItem = editingIdx !== null ? items[editingIdx] : null;
  const sectionWidth = step === "editing" ? "max-w-6xl" : "max-w-5xl";

  return (
    <section className={`mx-auto ${sectionWidth}`}>
      {/* Header */}
      <div className="mb-7">
        <h2 className="text-2xl font-bold tracking-tight text-gray-900">批量上傳</h2>
        <p className="mt-1 text-sm text-gray-500">
          {step === "review"
            ? "系統已自動偵測角點。低信心圖片建議手動調整後再送出。"
            : step === "editing"
              ? `調整角點：${editingItem?.prepared.filename ?? ""}`
              : "一次上傳多張稿紙圖片，最多 50 張。"}
        </p>
      </div>

      {/* Error */}
      {error && (
        <div
          className="mb-5 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          <svg className="mt-0.5 h-4 w-4 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          {error}
        </div>
      )}

      {/* ── Upload step ── */}
      {step === "upload" && (
        <div
          {...getRootProps({
            className: `
              group rounded-2xl border-2 border-dashed p-10 text-center transition-colors
              focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none
              ${isDragActive ? "border-indigo-500 bg-indigo-50/70" : "border-gray-300 bg-white/85 hover:border-indigo-300"}
              cursor-pointer
            `,
            role: "button",
            "aria-label": "上傳多張圖片",
          })}
        >
          <input {...getInputProps({ "aria-label": "上傳多張圖片" })} />
          <div className="flex flex-col items-center gap-3">
            <span className="rounded-full bg-indigo-100 p-3 text-indigo-600 transition-colors group-hover:bg-indigo-200">
              <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
            </span>
            <p className="text-sm font-medium text-gray-700">
              {isDragActive ? "放開以上傳圖片" : "拖曳多張圖片至此，或點擊選取檔案"}
            </p>
            <p className="text-xs text-gray-500">支援 PNG / JPG / WEBP / BMP / TIFF，最多 50 張</p>
          </div>
        </div>
      )}

      {/* ── Preparing spinner ── */}
      {step === "preparing" && (
        <div className="py-24 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50">
            <div className="h-7 w-7 rounded-full border-[3px] border-indigo-500 border-t-transparent motion-safe:animate-spin" />
          </div>
          <p className="text-sm font-medium text-gray-700">正在偵測角點…</p>
        </div>
      )}

      {/* ── Review grid ── */}
      {step === "review" && (
        <>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-gray-600">
              共{" "}
              <span className="font-semibold text-gray-900">{items.length}</span> 張 ·{" "}
              <span className="text-red-500 font-medium">
                {items.filter((it) => it.prepared.confidence < 0.4 && !it.overridden).length}
              </span>{" "}
              張需確認
            </p>
            <button
              onClick={reset}
              className="text-xs text-gray-400 hover:text-red-500 transition-colors"
            >
              重新上傳
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {items.map((it, idx) => {
              const { label, color } = confidenceLabel(
                it.overridden ? 1.0 : it.prepared.confidence,
              );
              return (
                <div
                  key={it.prepared.task_id}
                  className="group/card flex flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm"
                >
                  {/* Thumbnail */}
                  <div className="relative aspect-square overflow-hidden bg-gray-100">
                    <img
                      src={it.imageUrl}
                      alt={it.prepared.filename}
                      className="h-full w-full object-cover"
                    />
                    {/* Status overlay */}
                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent p-2">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${color}`}>
                        {it.overridden ? "已手動校正" : label}
                      </span>
                    </div>
                  </div>

                  {/* Footer */}
                  <div className="flex flex-col gap-1.5 p-2">
                    <p className="truncate text-[11px] font-medium text-gray-700">
                      {it.prepared.filename}
                    </p>
                    <button
                      onClick={() => openEditor(idx)}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 py-1 text-[11px] font-medium text-gray-600 transition-colors hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-200"
                    >
                      調整角點
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Submit bar */}
          <div className="mt-6 flex items-center justify-end gap-3">
            {items.some((it) => it.prepared.confidence < 0.4 && !it.overridden) && (
              <p className="text-xs text-amber-600">
                有低信心圖片尚未手動確認，建議先調整角點
              </p>
            )}
            <button
              onClick={handleSubmit}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-indigo-700 active:scale-95"
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L9 9.414V13a1 1 0 102 0V9.414l1.293 1.293a1 1 0 001.414-1.414z" clipRule="evenodd" />
              </svg>
              開始辨識 ({items.length} 張)
            </button>
          </div>
        </>
      )}

      {/* ── Corner editor ── */}
      {step === "editing" && editingItem && (
        <div className="rounded-2xl border border-gray-200 bg-white/85 p-4 shadow-sm sm:p-6">
          <CornerEditor
            key={`${editingItem.prepared.task_id}-${editingItem.corners.map((p) => `${p.x}-${p.y}`).join("|")}`}
            imageUrl={editingItem.imageUrl}
            corners={editingItem.corners}
            onConfirm={handleEditorConfirm}
            onSkip={handleEditorSkip}
          />
        </div>
      )}

      {/* ── Submitting spinner ── */}
      {step === "submitting" && (
        <div className="py-24 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50">
            <div className="h-7 w-7 rounded-full border-[3px] border-indigo-500 border-t-transparent motion-safe:animate-spin" />
          </div>
          <p className="text-sm font-medium text-gray-700">正在提交辨識任務…</p>
          <p className="mt-1 text-xs text-gray-400">任務啟動後會自動跳轉</p>
        </div>
      )}
    </section>
  );
}
