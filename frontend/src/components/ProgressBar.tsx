/** Progress bar with shimmer (indeterminate) and smooth fill. */

interface Props {
  progress: number; // 0–1
  stage?: string;
}

export default function ProgressBar({ progress, stage }: Props) {
  const pct = Math.round(progress * 100);
  const isIndeterminate = pct === 0;

  return (
    <div className="w-full rounded-2xl border border-indigo-100 bg-white/95 p-5 shadow-md">
      {/* Stage row */}
      <div className="mb-3 flex items-center gap-2">
        {/* Spinner */}
        <span className="inline-block h-4 w-4 flex-shrink-0 rounded-full border-2 border-indigo-400 border-t-transparent motion-safe:animate-spin" />
        <p className="text-sm font-medium text-indigo-700 tracking-wide">
          {stage || "處理中…"}
        </p>
        <span className="ml-auto text-xs font-semibold tabular-nums text-indigo-400">
          {isIndeterminate ? "—" : `${pct}%`}
        </span>
      </div>

      {/* Track */}
      <div
        className="relative h-2.5 w-full overflow-hidden rounded-full bg-indigo-50"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label="OCR 進度"
      >
        {isIndeterminate ? (
          /* Shimmer sweep when no progress yet */
          <div className="absolute inset-y-0 w-1/3 rounded-full bg-gradient-to-r from-transparent via-indigo-400 to-transparent animate-shimmer" />
        ) : (
          /* Filled bar */
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-blue-500 transition-[width] duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  );
}
