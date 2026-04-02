/**
 * ResultPage — live progress via WebSocket + side-by-side results view.
 * URL: /result?taskId=xxx
 */

import { useSearchParams, Link, useLocation } from "react-router-dom";
import { useState } from "react";
import { useOCRProgress } from "../hooks/useOCRProgress";
import ProgressBar from "../components/ProgressBar";
import ManuscriptView from "../components/ManuscriptView";
import ZoomableImage from "../components/ZoomableImage";
import ExportMenu from "../components/ExportMenu";
import { exportSingleJson, exportSingleTxt } from "../lib/export";

interface ResultLocationState {
  originalImageUrl?: string;
  originalFileName?: string;
}

export default function ResultPage() {
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<"linear" | "manuscript">("linear");
  const location = useLocation();
  const locationState = location.state as ResultLocationState | null;
  const originalImageUrl = locationState?.originalImageUrl ?? "";
  const originalFileName = locationState?.originalFileName ?? "原始圖像";
  const [params] = useSearchParams();
  const taskId = params.get("taskId");
  const { status, progress, stage, title, text, columns, error, elapsed } =
    useOCRProgress(taskId);

  if (!taskId) {
    return (
      <div className="mx-auto max-w-2xl py-24 text-center">
        <p className="text-4xl mb-4">📄</p>
        <p className="text-gray-500">尚未提交辨識任務</p>
        <Link
          to="/"
          className="mt-4 inline-block text-sm font-medium text-indigo-600 hover:text-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
        >
          返回上傳
        </Link>
      </div>
    );
  }

  const isProcessing = status === "pending" || status === "processing";
  const isFailed = status === "failed";
  const isDone = status === "completed";

  const copyText = async () => {
    const full = title ? `${title}\n${text}` : (text ?? "");
    await navigator.clipboard.writeText(full);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <section className="mx-auto max-w-6xl">
      {/* ── Header row ── */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-gray-900">辨識結果</h2>
          <p className="mt-0.5 text-sm text-gray-500">可即時查看進度，完成後一鍵複製文字。</p>
        </div>

        {/* Status badge + meta */}
        <div className="flex items-center gap-3">
          {elapsed !== null && (
            <span className="text-xs text-gray-400">耗時 {elapsed}s</span>
          )}
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
              isDone
                ? "bg-emerald-100 text-emerald-700"
                : isFailed
                  ? "bg-red-100 text-red-600"
                  : "bg-amber-100 text-amber-700"
            }`}
          >
            {isProcessing && (
              <span className="h-2 w-2 rounded-full bg-amber-400 motion-safe:animate-pulse" />
            )}
            {isDone ? "已完成" : isFailed ? "失敗" : "處理中"}
          </span>
        </div>
      </div>

      {/* ── Progress ── */}
      {isProcessing && (
        <div className="mb-6">
          <ProgressBar progress={progress} stage={stage} />
        </div>
      )}

      {/* ── Error ── */}
      {isFailed && error && (
        <div
          className="mb-6 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          role="alert"
        >
          <svg className="mt-0.5 h-4 w-4 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <div>
            <p className="font-medium">辨識失敗</p>
            <p className="mt-0.5 text-red-600">{error}</p>
          </div>
        </div>
      )}

      {/* ── Result ── */}
      {isDone && text !== null && (
        <>
          {/* Top-bottom layout */}
          <div className="flex flex-col gap-4">
            {/* Left – original image */}
            <div className="flex flex-col rounded-2xl border border-gray-200 bg-white/90 p-5 shadow-sm">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-400">
                原始圖像
              </h3>
              {originalImageUrl ? (
                <ZoomableImage
                  src={originalImageUrl}
                  alt={originalFileName}
                  className="h-[80vh] w-full"
                />
              ) : (
                <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-gray-200 bg-gray-50 p-8 text-sm text-gray-400">
                  未取得原始圖像
                  <br />
                  <span className="text-xs">(重新整理頁面或直接開啟結果連結)</span>
                </div>
              )}
            </div>

            {/* Right – OCR text */}
            <div className="flex flex-col rounded-2xl border border-gray-200 bg-white/90 p-5 shadow-sm">
              {/* View mode toggle */}
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400">
                  辨識文字
                </h3>
                <div className="flex overflow-hidden rounded-lg border border-gray-200 text-xs font-medium">
                  {(["linear", "manuscript"] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setViewMode(mode)}
                      className={`px-3 py-1.5 transition-colors ${
                        viewMode === mode
                          ? "bg-indigo-600 text-white"
                          : "bg-white text-gray-600 hover:bg-gray-50"
                      } ${mode === "manuscript" ? "border-l border-gray-200" : ""}`}
                    >
                      {mode === "linear" ? "橫排" : "稿紙直書"}
                    </button>
                  ))}
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-auto">
                {viewMode === "linear" ? (
                  <>
                    {title && (
                      <p className="mb-3 text-center text-lg font-bold tracking-widest text-gray-900 border-b border-gray-100 pb-3">
                        {title}
                      </p>
                    )}
                    <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-gray-50 p-4 font-sans text-base leading-loose text-gray-800">
                      {text}
                    </pre>
                  </>
                ) : (
                  <ManuscriptView columns={columns} />
                )}
              </div>
            </div>
          </div>

          {/* ── Action row ── */}
          <div className="mt-5 flex items-center justify-between">
            <Link
              to="/"
              className="text-sm text-gray-500 hover:text-indigo-600 transition-colors focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
            >
              ← 上傳新圖片
            </Link>

            <div className="flex items-center gap-2">
              <ExportMenu
                options={[
                  {
                    label: "純文字 (.txt)",
                    onClick: () =>
                      exportSingleTxt({ title, text, columns, rotation_angle: null, elapsed_seconds: elapsed, filename: originalFileName }),
                  },
                  {
                    label: "結構化資料 (.json)",
                    onClick: () =>
                      exportSingleJson({ title, text, columns, rotation_angle: null, elapsed_seconds: elapsed, filename: originalFileName }),
                  },
                ]}
              />

              <button
                onClick={copyText}
                className={`inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all duration-200 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none ${
                  copied
                    ? "bg-emerald-500 scale-95"
                    : "bg-indigo-600 hover:bg-indigo-700 active:scale-95"
                }`}
              >
                {copied ? (
                  <>
                    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    已複製！
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M8 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z" />
                      <path d="M6 3a2 2 0 00-2 2v11a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2 3 3 0 01-3 3H9a3 3 0 01-3-3z" />
                    </svg>
                    複製文字
                  </>
                )}
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Processing placeholder ── */}
      {isProcessing && (
        <div className="mt-4 rounded-2xl border border-gray-200 bg-white/60 p-10 text-center text-sm text-gray-400">
          辨識完成後結果將顯示於此
        </div>
      )}

      {/* Back link when not done */}
      {!isDone && (
        <div className="mt-6">
          <Link
            to="/"
            className="text-sm text-gray-500 hover:text-indigo-600 transition-colors focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
          >
            ← 上傳新圖片
          </Link>
        </div>
      )}
    </section>
  );
}
