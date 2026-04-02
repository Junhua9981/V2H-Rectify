/** Client-side export helpers — trigger browser downloads without a backend round-trip. */

import type { ColumnData } from "./types";

function download(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Single result
// ---------------------------------------------------------------------------

export interface SingleExportData {
  title: string | null;
  text: string | null;
  columns: ColumnData[];
  rotation_angle: number | null;
  elapsed_seconds: number | null;
  filename?: string;  // used as the base name for the downloaded file
}

export function exportSingleTxt(data: SingleExportData) {
  const parts: string[] = [];
  if (data.title) parts.push(data.title);
  if (data.text) parts.push(data.text);
  const base = data.filename?.replace(/\.[^.]+$/, "") ?? "ocr_result";
  download(`${base}.txt`, parts.join("\n"), "text/plain;charset=utf-8");
}

export function exportSingleJson(data: SingleExportData) {
  const payload = {
    title: data.title ?? null,
    text: data.text ?? null,
    columns: data.columns,
    rotation_angle: data.rotation_angle ?? null,
    elapsed_seconds: data.elapsed_seconds ?? null,
  };
  const base = data.filename?.replace(/\.[^.]+$/, "") ?? "ocr_result";
  download(`${base}.json`, JSON.stringify(payload, null, 2), "application/json");
}

// ---------------------------------------------------------------------------
// Batch result
// ---------------------------------------------------------------------------

export interface BatchExportItem {
  task_id: string;
  filename: string;
  title: string | null;
  text: string | null;
  columns: ColumnData[];
  rotation_angle: number | null;
  elapsed_seconds: number | null;
}

export function exportBatchTxt(items: BatchExportItem[]) {
  const parts = items
    .filter((it) => it.text)
    .map((it) => {
      const header = `=== ${it.filename} ===`;
      const body = it.title ? `${it.title}\n${it.text}` : (it.text ?? "");
      return `${header}\n${body}`;
    });
  download("batch_ocr_result.txt", parts.join("\n\n"), "text/plain;charset=utf-8");
}

export function exportBatchJson(items: BatchExportItem[]) {
  const payload = items.map((it) => ({
    filename: it.filename,
    title: it.title ?? null,
    text: it.text ?? null,
    columns: it.columns,
    rotation_angle: it.rotation_angle ?? null,
    elapsed_seconds: it.elapsed_seconds ?? null,
  }));
  download("batch_ocr_result.json", JSON.stringify(payload, null, 2), "application/json");
}
