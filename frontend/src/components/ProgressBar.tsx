/** Progress bar component */

interface Props {
  progress: number; // 0-1
  stage?: string;
}

export default function ProgressBar({ progress, stage }: Props) {
  const pct = Math.round(progress * 100);

  return (
    <div className="w-full rounded-xl border border-gray-200 bg-white/90 p-4 shadow-sm">
      {stage && (
        <p className="mb-2 text-xs font-medium text-gray-600">{stage}</p>
      )}
      <div
        className="h-3 w-full overflow-hidden rounded-full bg-gray-200"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label="OCR 進度"
      >
        <div
          className="h-3 rounded-full bg-gradient-to-r from-indigo-500 to-blue-500 transition-[width] duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2 text-right text-xs font-medium text-gray-500">{pct}%</p>
    </div>
  );
}
