/** Shared TypeScript types — mirrors backend api/schemas.py */

export interface Point {
  x: number;
  y: number;
}

export type TaskStatus = "pending" | "processing" | "completed" | "failed";

// -- Corner --

export interface CornerDetectResponse {
  corners: Point[];
  confidence: number;
  preview_url: string;
}

export interface CornerCorrectRequest {
  task_id: string;
  corners: Point[];
}

export interface CornerCorrectResponse {
  corrected: boolean;
  preview_url: string;
}

// -- OCR --

export interface ColumnData {
  col_index: number;
  text: string;
  spacing_indexes: number[];
  num_rows: number;
}

export interface OCRSubmitResponse {
  task_id: string;
  status: TaskStatus;
}

export interface OCRStatusResponse {
  task_id: string;
  status: TaskStatus;
  progress: number;
  title: string | null;
  text: string | null;
  columns: ColumnData[];
  rotation_angle: number | null;
  elapsed_seconds: number | null;
  error: string | null;
}

// -- Health --

export interface HealthResponse {
  status: string;
  craft_loaded: boolean;
  vlm_backend: string;
  version: string;
}

// -- WebSocket progress --

export interface WSProgressMessage {
  task_id: string;
  stage: string;
  progress: number;
  message: string;
}
