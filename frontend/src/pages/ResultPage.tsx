/**
 * ResultPage — polls OCR status + shows live progress via WebSocket.
 *
 * URL: /result?taskId=xxx
 */

import { useSearchParams, Link, useLocation } from "react-router-dom";
import { useState } from "react";
import { useOCRProgress } from "../hooks/useOCRProgress";
import ProgressBar from "../components/ProgressBar";
import ManuscriptView from "../components/ManuscriptView";

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
  const { status, progress, stage, title, text, columns, error, elapsed } = useOCRProgress(taskId);

  if (!taskId) {
    return (
      <div className="mx-auto max-w-2xl py-20 text-center">
        <p className="text-gray-500">尚未提交辨識任務</p>
        <Link
          to="/"
          className="mt-4 inline-block text-sm text-indigo-600 transition-colors hover:text-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
        >
          返回上傳
        </Link>
      </div>
    );
  }

  const isProcessing = status === "pending" || status === "processing";
  const isFailed = status === "failed";
  const isDone = status === "completed";

  const statusText = isDone ? "已完成" : isFailed ? "失敗" : "處理中";

  return (
    <section className="mx-auto max-w-4xl">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold tracking-tight text-gray-900">辨識結果</h2>
        <p className="mt-1 text-sm text-gray-600">可即時查看進度，完成後一鍵複製文字。</p>
      </div>

      {/* Task info */}
      <div className="mb-4 flex items-center justify-between rounded-xl border border-gray-200 bg-white/90 p-4 shadow-sm">
        <span className="font-mono text-xs text-gray-500">Task: {taskId}</span>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            isDone
              ? "bg-green-100 text-green-700"
              : isFailed
                ? "bg-red-100 text-red-700"
                : "bg-yellow-100 text-yellow-700"
          }`}
        >
          {statusText}
        </span>
      </div>

      {/* Progress */}
      {isProcessing && (
        <div className="mb-6">
          <ProgressBar progress={progress} stage={stage} />
        </div>
      )}

      {/* Error */}
      {isFailed && error && (
        <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          辨識失敗：{error}
        </div>
      )}

      {/* Result */}
      {isDone && text !== null && (
        <div className="space-y-4">
          <div className="space-y-4">
            <div className="rounded-xl border border-gray-200 bg-white/90 p-5 shadow-sm">
              <h3 className="mb-2 text-sm font-medium text-gray-500">原始圖像</h3>
              {originalImageUrl ? (
                <img
                  src={originalImageUrl}
                  alt={originalFileName}
                  className="max-h-[60vh] w-full rounded-lg border border-gray-100 bg-gray-50 object-contain"
                />
              ) : (
                <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-6 text-sm text-gray-500">
                  未取得原始圖像（可能是重新整理頁面或直接開啟結果連結）
                </div>
              )}
            </div>

            <div className="rounded-xl border border-gray-200 bg-white/90 p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-medium text-gray-500">辨識文字</h3>
                {/* View mode toggle */}
                <div className="flex overflow-hidden rounded-lg border border-gray-200 text-xs">
                  <button
                    onClick={() => setViewMode("linear")}
                    className={`px-3 py-1 transition-colors ${
                      viewMode === "linear"
                        ? "bg-indigo-600 text-white"
                        : "bg-white text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    橫排
                  </button>
                  <button
                    onClick={() => setViewMode("manuscript")}
                    className={`border-l border-gray-200 px-3 py-1 transition-colors ${
                      viewMode === "manuscript"
                        ? "bg-indigo-600 text-white"
                        : "bg-white text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    稿紙直書
                  </button>
                </div>
              </div>

              {viewMode === "linear" ? (
                <>
                  {title && (
                    <>
                      <p className="py-3 text-center text-lg font-semibold tracking-widest text-gray-900">
                        {title}
                      </p>
                      <hr className="my-3 border-gray-200" />
                    </>
                  )}
                  <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-4 font-sans text-base leading-relaxed text-gray-800">
                    {text}
                  </pre>
                </>
              ) : (
                <ManuscriptView columns={columns} />
              )}
            </div>
          </div>

          {/* Meta */}
          <div className="flex gap-6 text-xs text-gray-500">
            {elapsed !== null && <span>耗時 {elapsed}s</span>}
          </div>

          {/* Copy button */}
          <button
            onClick={async () => {
              const full = title ? `${title}\n${text}` : (text ?? "");
              await navigator.clipboard.writeText(full);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            }}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
          >
            {copied ? "已複製" : "複製文字"}
          </button>
        </div>
      )}

      {/* Back */}
      <div className="mt-8">
        <Link
          to="/"
          className="text-sm text-indigo-600 transition-colors hover:text-indigo-700 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
        >
          ← 上傳新圖片
        </Link>
      </div>
    </section>
  );
}
