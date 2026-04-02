# V2H-Rectify 交接文件

> 最後更新：2026-04-02

---

## 1. 專案概覽

**V2H-Rectify**（Vertical-to-Horizontal Rectify）是繁體中文手寫稿紙 OCR 系統，核心能力如下：

1. 稿紙角點偵測與透視校正
2. 傾斜校正、印刷文字移除
3. CRAFT 文字區塊偵測
4. 直排欄位重排與 VLM 文字辨識
5. 單張與批量 OCR 任務追蹤

---

## 2. 系統架構

### 2.1 三服務

- `frontend`（Nginx，host:3000）
- `backend`（FastAPI，host:8080）
- `vllm`（OpenAI-compatible，host:8001）

### 2.2 單張 OCR 流程

1. `POST /api/v1/corner/detect`
2. `POST /api/v1/corner/correct`（可選）
3. `POST /api/v1/ocr/upload`
4. `WS /api/v1/ws/{task_id}` + `GET /api/v1/ocr/{task_id}`

### 2.3 批量 OCR 流程（已上線）

1. `POST /api/v1/ocr/batch/prepare`（多檔角點偵測）
2. 前端可逐張調整角點
3. `POST /api/v1/ocr/batch/submit`（送出整批）
4. `WS /api/v1/ws/batch/{batch_id}` + `GET /api/v1/ocr/batch/{batch_id}`

---

## 3. 後端導覽

### 3.1 主要檔案

- `backend/api/app.py`：app factory + lifespan
- `backend/api/schemas.py`：單張/批量 schemas
- `backend/api/ws.py`：單張 + 批量 WS 廣播
- `backend/api/routes/ocr.py`：單張/批量 OCR routes
- `backend/services/ocr_pipeline.py`：OCR 流程編排
- `backend/core/text_reformat.py`：直排轉橫排與空白格判定

### 3.2 API 一覽

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/api/v1/corner/detect` | 單張角點偵測 |
| POST | `/api/v1/corner/correct` | 單張透視校正 |
| POST | `/api/v1/ocr/upload` | 單張 OCR 提交 |
| GET | `/api/v1/ocr/{task_id}` | 單張 OCR 狀態 |
| POST | `/api/v1/ocr/batch/prepare` | 批量角點預處理 |
| POST | `/api/v1/ocr/batch/submit` | 批量 OCR 提交 |
| GET | `/api/v1/ocr/batch/{batch_id}` | 批量 OCR 狀態 |
| WS | `/api/v1/ws/{task_id}` | 單張進度推播 |
| WS | `/api/v1/ws/batch/{batch_id}` | 批量進度推播 |
| GET | `/api/v1/health` | 健康檢查 |

### 3.3 任務狀態儲存

- `_pending_images`：角點流程暫存
- `_tasks`：單張任務狀態
- `_batches`：批量任務索引

以上皆為 in-memory，重啟遺失。

### 3.4 OCRPipeline 階段

- `0.10`：偵測文字區塊
- `0.25`：校正傾斜
- `0.40`：移除印刷文字
- `0.55`：提取格線結構
- `0.65`：重新格式化版面
- `0.65-0.95`：辨識第 N 欄
- `1.00`：完成

### 3.5 text_reformat 目前狀態

- `TextReformatConfig` 維持 4 個參數
- 已套用中心熱圖裁切 `_HEAT_CENTER_MARGIN = 0.20`
- 目的：降低鄰近字元 heatmap 擴散造成的空白格誤判

### 3.6 版本注意

後端 `FastAPI version` 與 `HealthResponse.version` 目前為 `3.0.0`。

---

## 4. 前端導覽

### 4.1 路由

- `/` → `UploadPage`
- `/result` → `ResultPage`
- `/batch` → `BatchUploadPage`
- `/batch/result` → `BatchResultPage`

### 4.2 主要頁面

- `UploadPage`：單張上傳三步驟
- `ResultPage`：單張進度 + 結果視圖
- `BatchUploadPage`：多圖上傳 + 逐張角點覆寫
- `BatchResultPage`：整批進度 + 逐張結果 + 匯出

### 4.3 主要元件與 Hook

- `components/ZoomableImage.tsx`
- `components/CornerEditor.tsx`
- `components/ExportMenu.tsx`
- `hooks/useOCRProgress.ts`
- `hooks/useBatchProgress.ts`

### 4.4 API 客戶端

`frontend/src/lib/api.ts` 目前包含：

- 單張：`detectCorners`、`correctCorners`、`submitOCR`、`pollOCRStatus`、`connectProgressWS`
- 批量：`prepareBatch`、`submitBatch`、`pollBatchStatus`、`connectBatchProgressWS`

`frontend/src/lib/export.ts` 提供批量 txt/json 匯出。

---

## 5. 開發與部署

### 5.1 本地開發

```bash
cd backend
cp .env.example .env
pip install -e ".[dev]"
uvicorn api.app:app --host 127.0.0.1 --port 8080 --reload

cd frontend
npm install
npm run dev
```

### 5.2 Docker

```bash
cp backend/.env.example backend/.env
docker compose up --build -d
```

---

## 6. 已知問題與技術債

| # | 類別 | 說明 | 影響 |
|---|---|---|---|
| 1 | 任務持久化 | `_tasks/_pending_images/_batches` 為 in-memory，重啟遺失 | 中 |
| 2 | Docker 驗證 | compose 尚未在乾淨環境完整驗證 | 中 |
| 3 | CI/CD | 尚未建立 lint/test/build 自動化 | 中 |
| 4 | CORS | `allow_origins=["*"]`，生產需收斂 | 低 |
| 5 | 批次 UX | `batch/submit` 回傳 task `filename` 為空字串，可補強追蹤 | 低 |

---

## 7. 建議優先順序

1. 任務持久化（Redis）
2. Docker 乾淨環境驗證
3. CI/CD（ruff + pytest + docker build）
4. CORS 白名單化
5. 批次流程 UX（失敗重試、檔名追蹤）

---

## 8. 維護 SOP

### 8.1 切換 VLM 後端

1. `backend/.env` 設定 `VLM__BACKEND=vllm|gemini|openai`
2. 填入對應 API key
3. 重啟 backend

### 8.2 調整 OCR 參數

- 修改 `backend/config/settings.py` (`OCRPipelineSettings`)
- 或使用 `PIPELINE__*` 環境變數覆蓋

### 8.3 新增 API

1. 新增 `backend/api/routes/*.py`
2. 建立 `APIRouter`
3. 在 `backend/api/app.py` 註冊
4. 同步 `backend/api/schemas.py` 與 `frontend/src/lib/types.ts`

---

## 9. 分支備註

- `main`：穩定基線
- `feat/websocket-progress`：WS 進度整合
- `feat/zoomable-image`（目前分支）：含 ZoomableImage 與批量流程前端頁面
