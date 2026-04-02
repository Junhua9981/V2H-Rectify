/** API client — all backend calls in one place. */

import type {
  BatchPrepareResponse,
  BatchStatusResponse,
  BatchSubmitRequest,
  BatchSubmitResponse,
  CornerCorrectRequest,
  CornerCorrectResponse,
  CornerDetectResponse,
  HealthResponse,
  OCRStatusResponse,
  OCRSubmitResponse,
} from "./types";

const BASE = "/api/v1";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// -- Health --

export async function fetchHealth(): Promise<HealthResponse> {
  return json<HealthResponse>(await fetch(`${BASE}/health`));
}

// -- Corner --

export async function detectCorners(file: File): Promise<CornerDetectResponse & { task_id: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/corner/detect`, { method: "POST", body: fd });
  const data = await json<CornerDetectResponse>(res);
  const dataWithTask = data as CornerDetectResponse & { task_id?: string };
  // The task_id is not in CornerDetectResponse schema — we extract it from
  // the response body. Backend should include it; if not, we generate one.
  return { ...data, task_id: dataWithTask.task_id ?? "" };
}

export async function correctCorners(req: CornerCorrectRequest): Promise<CornerCorrectResponse> {
  return json<CornerCorrectResponse>(
    await fetch(`${BASE}/corner/correct`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  );
}

// -- OCR --

export async function submitOCR(
  file: File,
  opts?: { auto_rotate?: boolean; remove_print?: boolean; auto_split?: boolean; task_id?: string },
): Promise<OCRSubmitResponse> {
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.auto_rotate !== undefined) fd.append("auto_rotate", String(opts.auto_rotate));
  if (opts?.remove_print !== undefined) fd.append("remove_print", String(opts.remove_print));
  if (opts?.auto_split !== undefined) fd.append("auto_split", String(opts.auto_split));
  if (opts?.task_id) fd.append("task_id", opts.task_id);
  return json<OCRSubmitResponse>(await fetch(`${BASE}/ocr/upload`, { method: "POST", body: fd }));
}

export async function pollOCRStatus(taskId: string): Promise<OCRStatusResponse> {
  return json<OCRStatusResponse>(await fetch(`${BASE}/ocr/${taskId}`));
}

// -- Batch OCR --

export async function prepareBatch(files: File[]): Promise<BatchPrepareResponse> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  return json<BatchPrepareResponse>(await fetch(`${BASE}/ocr/batch/prepare`, { method: "POST", body: fd }));
}

export async function submitBatch(req: BatchSubmitRequest): Promise<BatchSubmitResponse> {
  return json<BatchSubmitResponse>(
    await fetch(`${BASE}/ocr/batch/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  );
}

export async function pollBatchStatus(batchId: string): Promise<BatchStatusResponse> {
  return json<BatchStatusResponse>(await fetch(`${BASE}/ocr/batch/${batchId}`));
}

// -- WebSocket --

export function connectProgressWS(taskId: string): WebSocket {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return new WebSocket(`${proto}//${window.location.host}${BASE}/ws/${taskId}`);
}

export function connectBatchProgressWS(batchId: string): WebSocket {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return new WebSocket(`${proto}//${window.location.host}${BASE}/ws/batch/${batchId}`);
}
