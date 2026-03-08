/** ImageDropzone — drag-and-drop file upload area. */

import { useCallback } from "react";
import { useDropzone } from "react-dropzone";

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
}

export default function ImageDropzone({ onFile, disabled }: Props) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) onFile(accepted[0]);
    },
    [onFile],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/*": [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"] },
    maxFiles: 1,
    disabled,
  });

  return (
    <div
      {...getRootProps({
        className: `
          group rounded-2xl border-2 border-dashed p-10 text-center transition-colors
          focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none
          ${isDragActive ? "border-indigo-500 bg-indigo-50/70" : "border-gray-300 bg-white/85 hover:border-indigo-300"}
          ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}
        `,
        role: "button",
        "aria-label": "上傳圖片檔案",
      })}
    >
      <input {...getInputProps({ "aria-label": "上傳圖片檔案" })} />
      <div className="flex flex-col items-center gap-3">
        <span className="rounded-full bg-indigo-100 p-3 text-indigo-600 transition-colors group-hover:bg-indigo-200">
          <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
            />
          </svg>
        </span>
        <p className="text-sm font-medium text-gray-700">
          {isDragActive ? "放開以上傳圖片" : "拖曳圖片至此，或點擊選取檔案"}
        </p>
        <p className="text-xs text-gray-500">支援 PNG / JPG / WEBP / BMP / TIFF，建議清晰拍攝</p>
      </div>
    </div>
  );
}
