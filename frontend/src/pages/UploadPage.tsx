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
        state: {
          originalImageUrl: imageUrl,
          originalFileName: file.name,
        },
      });
    } catch (error: unknown) {
      setError(`OCR 啟動失敗：${getErrorMessage(error)}`);
      setStep("upload");
    }
  };

  const sectionWidthClass = step === "corner" ? "max-w-6xl" : "max-w-4xl";

  return (
    <section className={`mx-auto ${sectionWidthClass}`}>
      <div className="mb-6">
        <h2 className="text-2xl font-semibold tracking-tight text-gray-900">上傳稿紙圖片</h2>
        <p className="mt-1 text-sm text-gray-600">上傳後可手動微調角點，再送出 OCR 辨識。</p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-2 text-xs font-medium">
        <span
          className={`rounded-full px-3 py-1 ${step === "upload" ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-500"}`}
        >
          1. 上傳圖片
        </span>
        <span className="text-gray-300">→</span>
        <span
          className={`rounded-full px-3 py-1 ${step === "corner" ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-500"}`}
        >
          2. 校正角點
        </span>
        <span className="text-gray-300">→</span>
        <span
          className={`rounded-full px-3 py-1 ${step === "submitting" ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-500"}`}
        >
          3. 提交任務
        </span>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          {error}
        </div>
      )}

      <div className="rounded-2xl border border-gray-200 bg-white/80 p-4 shadow-sm sm:p-6">
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
          <div className="py-16 text-center">
            <div className="inline-block h-8 w-8 rounded-full border-4 border-indigo-600 border-t-transparent motion-safe:animate-spin" />
            <p className="mt-4 text-sm text-gray-600">正在提交辨識任務…</p>
          </div>
        )}
      </div>
    </section>
  );
}
