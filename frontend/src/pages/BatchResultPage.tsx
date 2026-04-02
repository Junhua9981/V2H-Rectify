/**
 * BatchResultPage — aggregated progress + per-task results for batch OCR.
 * URL: /batch/result?batchId=xxx
 */

import { useSearchParams, Link, useLocation } from "react-router-dom";
import { useState } from "react";
import { useBatchProgress } from "../hooks/useBatchProgress";
import ProgressBar from "../components/ProgressBar";
import ExportMenu from "../components/ExportMenu";
import { exportBatchJson, exportBatchTxt } from "../lib/export";

interface BatchLocationState {
  imageUrls?: Record<string, string>;
  filenames?: Record<string, string>;
}

export default function BatchResultPage() {
  const [params] = useSearchParams();
  const batchId = params.get("batchId");
  const location = useLocation();
  const locationState = location.state as BatchLocationState | null;
  const imageUrls = locationState?.imageUrls ?? {};
  const filenames = locationState?.filenames ?? {};
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedAll, setCopiedAll] = useState(false);

  const { total, completed, failed, progress, tasks, done } = useBatchProgress(batchId);

  if (!batchId) {
    return (
      <div className="mx-auto max-w-2xl py-24 text-center">
        <p className="text-4xl mb-4">📄</p>
        <p className="text-gray-500">尚未提交批量辨識任務</p>
        <Link
          to="/batch"
          className="mt-4 inline-block text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          前往批量上傳
        </Link>
      </div>
    );
  }

  const copyOne = async (taskId: string) => {
    const task = tasks.find((t) => t.task_id === taskId);
    if (!task) return;
    const full = task.title ? `${task.title}\n${task.text}` : (task.text ?? "");
    await navigator.clipboard.writeText(full);
    setCopiedId(taskId);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const copyAll = async () => {
    const allText = tasks
      .filter((t) => t.status === "completed" && t.text)
      .map((t, i) => {
        const name = filenames[t.task_id] || `圖片 ${i + 1}`;
        const header = `=== ${name} ===`;
        const body = t.title ? `${t.title}\n${t.text}` : (t.text ?? "");
        return `${header}\n${body}`;
      })
      .join("\n\n");
    await navigator.clipboard.writeText(allText);
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), 1800);
  };

  const buildExportItems = () =>
    tasks
      .filter((t) => t.status === "completed")
      .map((t, i) => ({
        task_id: t.task_id,
        filename: filenames[t.task_id] || `圖片 ${i + 1}`,
        title: t.title ?? null,
        text: t.text ?? null,
        columns: t.columns ?? [],
        rotation_angle: t.rotation_angle ?? null,
        elapsed_seconds: t.elapsed_seconds ?? null,
      }));

  const isProcessing = !done;

  return (
    <section className="mx-auto max-w-6xl">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-gray-900">批量辨識結果</h2>
          <p className="mt-0.5 text-sm text-gray-500">
            共 {total} 張，已完成 {completed}，失敗 {failed}
          </p>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
            done
              ? failed === 0
                ? "bg-emerald-100 text-emerald-700"
                : "bg-amber-100 text-amber-700"
              : "bg-amber-100 text-amber-700"
          }`}
        >
          {isProcessing && (
            <span className="h-2 w-2 rounded-full bg-amber-400 motion-safe:animate-pulse" />
          )}
          {done ? (failed === 0 ? "全部完成" : "部分失敗") : "處理中"}
        </span>
      </div>

      {/* Overall progress */}
      {isProcessing && (
        <div className="mb-6">
          <ProgressBar
            progress={progress}
            stage={`處理中 (${completed + failed}/${total})`}
          />
        </div>
      )}

      {/* Copy all + Export buttons */}
      {done && completed > 0 && (
        <div className="mb-5 flex justify-end gap-2">
          <ExportMenu
            options={[
              {
                label: "純文字 (.txt)",
                onClick: () => exportBatchTxt(buildExportItems()),
              },
              {
                label: "結構化資料 (.json)",
                onClick: () => exportBatchJson(buildExportItems()),
              },
            ]}
          />
          <button
            onClick={copyAll}
            className={`inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all duration-200 ${
              copiedAll
                ? "bg-emerald-500 scale-95"
                : "bg-indigo-600 hover:bg-indigo-700 active:scale-95"
            }`}
          >
            {copiedAll ? (
              <>
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
                已複製全部！
              </>
            ) : (
              <>
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M8 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z" />
                  <path d="M6 3a2 2 0 00-2 2v11a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2 3 3 0 01-3 3H9a3 3 0 01-3-3z" />
                </svg>
                複製全部文字
              </>
            )}
          </button>
        </div>
      )}

      {/* Task cards */}
      <div className="space-y-4">
        {tasks.map((task, idx) => {
          const filename = filenames[task.task_id] || `圖片 ${idx + 1}`;
          const imgUrl = imageUrls[task.task_id];
          const isTaskDone = task.status === "completed";
          const isTaskFailed = task.status === "failed";
          const isTaskProcessing = task.status === "processing" || task.status === "pending";

          return (
            <div
              key={task.task_id}
              className="rounded-2xl border border-gray-200 bg-white/90 shadow-sm overflow-hidden"
            >
              {/* Card header */}
              <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gray-100 text-xs font-bold text-gray-600">
                    {idx + 1}
                  </span>
                  <span className="text-sm font-medium text-gray-800 truncate max-w-xs">
                    {filename}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {isTaskProcessing && (
                    <div className="flex items-center gap-1.5">
                      <div className="h-3 w-3 rounded-full border-2 border-amber-400 border-t-transparent motion-safe:animate-spin" />
                      <span className="text-xs text-amber-600">
                        {Math.round(task.progress * 100)}%
                      </span>
                    </div>
                  )}
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      isTaskDone
                        ? "bg-emerald-100 text-emerald-700"
                        : isTaskFailed
                          ? "bg-red-100 text-red-600"
                          : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {isTaskDone ? "完成" : isTaskFailed ? "失敗" : "處理中"}
                  </span>
                </div>
              </div>

              {/* Card body */}
              {isTaskDone && task.text !== null && (
                <div className="flex gap-4 p-5">
                  {/* Thumbnail */}
                  {imgUrl && (
                    <div className="flex-shrink-0">
                      <img
                        src={imgUrl}
                        alt={filename}
                        className="h-28 w-28 rounded-lg object-cover border border-gray-200"
                      />
                    </div>
                  )}
                  {/* Text */}
                  <div className="min-w-0 flex-1">
                    {task.title && (
                      <p className="mb-2 text-sm font-bold text-gray-900">{task.title}</p>
                    )}
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 font-sans text-sm leading-relaxed text-gray-800">
                      {task.text}
                    </pre>
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        onClick={() => copyOne(task.task_id)}
                        className={`inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                          copiedId === task.task_id
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                        }`}
                      >
                        {copiedId === task.task_id ? "已複製" : "複製"}
                      </button>
                      {task.elapsed_seconds !== null && (
                        <span className="text-[10px] text-gray-400">
                          耗時 {task.elapsed_seconds}s
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Processing placeholder */}
              {isTaskProcessing && (
                <div className="px-5 py-4">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full bg-amber-400 transition-all duration-300"
                      style={{ width: `${Math.round(task.progress * 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Error */}
              {isTaskFailed && task.error && (
                <div className="px-5 py-4">
                  <p className="text-sm text-red-600">{task.error}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Processing placeholder for empty tasks */}
      {tasks.length === 0 && isProcessing && (
        <div className="mt-4 rounded-2xl border border-gray-200 bg-white/60 p-10 text-center text-sm text-gray-400">
          正在載入批量任務…
        </div>
      )}

      {/* Back link */}
      <div className="mt-6">
        <Link
          to="/batch"
          className="text-sm text-gray-500 hover:text-indigo-600 transition-colors"
        >
          ← 批量上傳新圖片
        </Link>
      </div>
    </section>
  );
}
