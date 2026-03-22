/**
 * UploadPage — the main workflow page.
 *
 * Flow:
 *   1. User drops an image → POST /corner/detect
 *   2. CornerEditor shown → user adjusts corners → POST /corner/correct
 *   3. POST /ocr/upload (with task_id from corner step)
 *   4. Navigate to /result?taskId=xxx
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import ImageDropzone from "../components/ImageDropzone";
import CornerEditor from "../components/CornerEditor";
import { correctCorners, detectCorners, submitOCR } from "../lib/api";
import type { Point } from "../lib/types";

type Step = "upload" | "corner" | "submitting";

const STEPS: { key: Step | "done"; label: string }[] = [
  { key: "upload", label: "上傳圖片" },
  { key: "corner", label: "校正角點" },
  { key: "submitting", label: "提交任務" },
];

function stepIndex(step: Step): number {
  return ["upload", "corner", "submitting"].indexOf(step);
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "請稍後再試";
}

export default function UploadPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [corners, setCorners] = useState<Point[]>([]);
  const [taskId, setTaskId] = useState("");
  const [error, setError] = useState("");

  const currentIdx = stepIndex(step);

  // Step 1: user drops a file
  const handleFile = async (f: File) => {
    setFile(f);
    setError("");
    setImageUrl(URL.createObjectURL(f));
    try {
      const res = await detectCorners(f);
      setCorners(res.corners);
      setTaskId(res.task_id);
      setStep("corner");
    } catch (error: unknown) {
      setError(`角點偵測失敗：${getErrorMessage(error)}`);
    }
  };

  // Step 2a: user confirms adjusted corners
  const handleCornerConfirm = async (pts: Point[]) => {
    setStep("submitting");
    try {
      await correctCorners({ task_id: taskId, corners: pts });
      await startOCR();
    } catch (error: unknown) {
      setError(`透視校正失敗：${getErrorMessage(error)}`);
      setStep("corner");
    }
  };

  // Step 2b: user skips corner correction
  const handleSkip = async () => {
    setStep("submitting");
    await startOCR();
  };

  // Step 3: submit OCR
  const startOCR = async () => {
    if (!file) return;
    try {
      const res = await submitOCR(file, { task_id: taskId || undefined });
      navigate(`/result?taskId=${res.task_id}`, {
        state: { originalImageUrl: imageUrl, originalFileName: file.name },
      });
    } catch (error: unknown) {
      setError(`OCR 啟動失敗：${getErrorMessage(error)}`);
      setStep("upload");
    }
  };

  const sectionWidthClass = step === "corner" ? "max-w-6xl" : "max-w-4xl";

  return (
    <section className={`mx-auto ${sectionWidthClass}`}>
      {/* Page header */}
      <div className="mb-7">
        <h2 className="text-2xl font-bold tracking-tight text-gray-900">上傳稿紙圖片</h2>
        <p className="mt-1 text-sm text-gray-500">上傳後可手動微調角點，再送出 OCR 辨識。</p>
      </div>

      {/* Step indicator */}
      <div className="mb-7 flex items-center">
        {STEPS.map((s, i) => {
          const done = i < currentIdx;
          const active = i === currentIdx;
          return (
            <div key={s.key} className="flex flex-1 items-center">
              <div className="flex flex-col items-center gap-1">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-bold transition-colors duration-300 ${
                    done
                      ? "border-indigo-500 bg-indigo-500 text-white"
                      : active
                        ? "border-indigo-500 bg-white text-indigo-600"
                        : "border-gray-300 bg-white text-gray-400"
                  }`}
                >
                  {done ? (
                    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </div>
                <span
                  className={`text-xs font-medium whitespace-nowrap ${
                    active ? "text-indigo-600" : done ? "text-indigo-400" : "text-gray-400"
                  }`}
                >
                  {s.label}
                </span>
              </div>
              {/* Connector */}
              {i < STEPS.length - 1 && (
                <div
                  className={`mx-2 mb-5 h-0.5 flex-1 rounded transition-colors duration-500 ${
                    done ? "bg-indigo-400" : "bg-gray-200"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-5 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          <svg className="mt-0.5 h-4 w-4 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          {error}
        </div>
      )}

      {/* Content card */}
      <div className="rounded-2xl border border-gray-200 bg-white/85 p-4 shadow-sm sm:p-6">
        {step === "upload" && <ImageDropzone onFile={handleFile} />}

        {step === "corner" && imageUrl && (
          <CornerEditor
            key={`${taskId}-${corners.map((p) => `${p.x}-${p.y}`).join("|")}`}
            imageUrl={imageUrl}
            corners={corners}
            onConfirm={handleCornerConfirm}
            onSkip={handleSkip}
          />
        )}

        {step === "submitting" && (
          <div className="py-20 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50">
              <div className="h-7 w-7 rounded-full border-[3px] border-indigo-500 border-t-transparent motion-safe:animate-spin" />
            </div>
            <p className="text-sm font-medium text-gray-700">正在提交辨識任務…</p>
            <p className="mt-1 text-xs text-gray-400">任務啟動後會自動跳轉</p>
          </div>
        )}
      </div>
    </section>
  );
}
