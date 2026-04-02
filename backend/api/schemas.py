"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# ---------------------------------------------------------------------------
# Corner detection / perspective correction
# ---------------------------------------------------------------------------

class Point(BaseModel):
    x: float
    y: float


class CornerDetectResponse(BaseModel):
    """Auto-detected corners of the essay paper."""
    task_id: str = ""
    corners: List[Point] = Field(..., min_length=4, max_length=4)
    confidence: float = Field(ge=0.0, le=1.0)
    preview_url: str = ""


class CornerCorrectRequest(BaseModel):
    """User-adjusted corners for perspective correction."""
    task_id: str
    corners: List[Point] = Field(..., min_length=4, max_length=4)


class CornerCorrectResponse(BaseModel):
    corrected: bool = True
    preview_url: str = ""


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

class OCROptions(BaseModel):
    auto_rotate: bool = True
    remove_print: bool = True
    auto_split: bool = True


class OCRSubmitResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.pending


class ColumnData(BaseModel):
    """Per-column OCR data for manuscript (稿紙) layout reconstruction."""
    col_index: int
    text: str
    spacing_indexes: List[int]
    num_rows: int


class OCRStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: float = Field(0.0, ge=0.0, le=1.0)
    title: Optional[str] = None
    text: Optional[str] = None
    columns: List[ColumnData] = Field(default_factory=list)
    rotation_angle: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Batch OCR
# ---------------------------------------------------------------------------

class BatchTaskItem(BaseModel):
    task_id: str
    filename: str
    status: TaskStatus = TaskStatus.pending

class BatchSubmitResponse(BaseModel):
    batch_id: str
    tasks: List[BatchTaskItem]

class BatchStatusResponse(BaseModel):
    batch_id: str
    total: int
    completed: int
    failed: int
    processing: int
    progress: float = Field(0.0, ge=0.0, le=1.0)
    tasks: List[OCRStatusResponse]


# ---------------------------------------------------------------------------
# Batch prepare (corner detection + manual override before OCR)
# ---------------------------------------------------------------------------

class BatchPrepareItem(BaseModel):
    task_id: str
    filename: str
    corners: List[Point]  # 4 points in original-image coordinates
    confidence: float = Field(ge=0.0, le=1.0)

class BatchPrepareResponse(BaseModel):
    items: List[BatchPrepareItem]

class BatchCorrectionItem(BaseModel):
    task_id: str
    corners: List[Point]  # final corners (auto or manually overridden)

class BatchSubmitRequest(BaseModel):
    corrections: List[BatchCorrectionItem]
    auto_rotate: bool = True
    remove_print: bool = True
    auto_split: bool = True


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    craft_loaded: bool = False
    vlm_backend: str = ""
    version: str = "3.0.0"


# ---------------------------------------------------------------------------
# WebSocket progress messages
# ---------------------------------------------------------------------------

class WSProgressMessage(BaseModel):
    task_id: str
    stage: str = ""
    progress: float = 0.0
    message: str = ""
    status: str = "processing"  # "processing" | "completed" | "failed"


class WSBatchProgressMessage(BaseModel):
    batch_id: str
    progress: float = 0.0
    completed: int = 0
    failed: int = 0
    total: int = 0
    status: str = "processing"  # "processing" | "completed"
