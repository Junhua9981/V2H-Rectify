# V2H-Rectify 交接文件

> 最後更新：2026-03-22

---

## 1. 專案概覽

**V2H-Rectify**（Vertical-to-Horizontal Rectify）是一套完整的 OCR 處理流程，用於：

1. 從掃描／拍攝的稿紙圖片中**偵測文件邊界**（角點偵測 + 透視校正）
2. **自動校正傾斜**、移除印刷文字
3. 以 CRAFT 偵測手寫文字區塊
4. 將**直排中文稿紙**切分為列，再透過 VLM（Vision Language Model）辨識每列文字
5. 輸出**橫排純文字** + **結構化稿紙欄位資料**

核心價值：將傳統繁體中文直排手寫稿紙轉為可編輯的橫排數位文字。

### 技術棧摘要

| 層級 | 技術 |
|---|---|
| 文字偵測 | CRAFT（透過 EasyOCR） |
| 文字辨識 (VLM) | vLLM（Qwen2.5-VL）/ Gemini / OpenAI — 可切換 |
| 後端 | Python 3.10+, FastAPI, PyTorch, OpenCV |
| 前端 | React 19, TypeScript, Vite 7, Tailwind CSS 4, Konva |
| 部署 | Docker Compose（vLLM + backend + frontend） |

---

## 2. 架構總覽

### 2.1 三服務拓撲

```
┌────────────┐      ┌─────────────┐      ┌────────────┐
│  frontend   │──▶──│   backend    │──▶──│    vLLM     │
│  (nginx)    │     │  (FastAPI)   │     │ (推論伺服器)│
│  Port 3000  │     │  Port 8080   │     │  Port 8001  │
└────────────┘      └─────────────┘      └────────────┘
    │                    │                     │
    │  /api/* proxy      │  CRAFT (GPU)        │  OpenAI compat API
    │  /ws/* upgrade     │  OpenCV pipeline     │  Qwen2.5-VL model
```

- **frontend**：Nginx 提供 React SPA 靜態檔，同時反向代理 `/api/*` 到 backend、`/api/v1/ws/*` 升級 WebSocket
- **backend**：FastAPI，掛載 CRAFT 模型（GPU），執行影像處理 pipeline，透過 OpenAI 相容 API 呼叫 VLM
- **vLLM**：OpenAI 相容推論伺服器，容器內 port 8000 → 對外 8001

### 2.2 請求生命週期

```
使用者上傳圖片
  │
  ▼
POST /corner/detect  →  角點偵測 → 回傳 4 角點 + task_id + confidence
  │
  ▼（使用者可在 Canvas 上微調角點）
POST /corner/correct →  透視校正 → 儲存已校正圖片
  │
  ▼
POST /ocr/upload     →  啟動 OCR 任務（背景執行）→ 回傳 task_id
  │
  ├── WS /ws/{task_id}       → 即時進度推送（stage, progress, status）
  └── GET /ocr/{task_id}     → 輪詢結果（每 2 秒，WS 完成時立即觸發）
  │
  ▼
回傳：{ title, text, columns[], rotation_angle, elapsed_seconds }
```

---

## 3. 後端模組導覽

### 3.1 目錄結構

```
backend/
├── api/                    # FastAPI 應用層
│   ├── app.py              # 應用工廠 + lifespan 管理
│   ├── deps.py             # 依賴注入（singleton services）
│   ├── schemas.py          # Pydantic 請求/回應模型
│   ├── ws.py               # WebSocket 進度廣播（現已主動使用）
│   └── routes/
│       ├── corner.py       # 角點偵測 + 透視校正路由
│       ├── ocr.py          # OCR 提交 + 狀態輪詢路由
│       └── health.py       # 健康檢查路由
├── config/
│   └── settings.py         # Pydantic Settings 集中配置
├── core/                   # 影像處理核心模組
│   ├── craft_detector.py   # CRAFT 文字偵測封裝
│   ├── grid_extractor.py   # 投影法格線偵測
│   ├── image_utils.py      # 格式轉換 + 圖片分割
│   ├── perspective.py      # 角點偵測 + 透視變換
│   ├── print_removal.py    # 印刷/手寫分類 + 移除
│   ├── rotation.py         # 多方法傾斜校正
│   └── text_reformat.py    # 直排→橫排轉換 + 空白格偵測（已簡化）
├── services/               # 業務服務層
│   ├── craft_service.py    # CRAFT 批次推論服務
│   ├── vlm_service.py      # VLM 多後端策略服務
│   └── ocr_pipeline.py     # OCR 全流程編排器（含進度回調）
├── tests/
│   └── test_text_reformat.py   # text_reformat 單元測試（9 個）
├── pyproject.toml          # Python 依賴 + 工具設定
├── Dockerfile              # Python 3.11 + OpenCV 系統依賴
└── .env.example            # 環境變數模板
```

### 3.2 API 層

#### Endpoints 總表

| 方法 | 路徑 | 功能 | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/corner/detect` | 自動偵測稿紙角點 | `multipart/form-data: file` | `CornerDetectResponse` |
| `POST` | `/api/v1/corner/correct` | 使用者微調後透視校正 | `CornerCorrectRequest (JSON)` | `CornerCorrectResponse` |
| `POST` | `/api/v1/ocr/upload` | 提交 OCR 辨識任務 | `multipart/form-data: file, auto_rotate, remove_print, auto_split, task_id` | `OCRSubmitResponse` |
| `GET` | `/api/v1/ocr/{task_id}` | 輪詢任務狀態與結果 | — | `OCRStatusResponse` |
| `WS` | `/api/v1/ws/{task_id}` | 即時進度推送 | — | `WSProgressMessage` (JSON) |
| `GET` | `/api/v1/health` | 系統健康檢查 | — | `HealthResponse` |

#### 依賴注入模式

- `app.py` 透過 `lifespan` context manager 初始化 `CRAFTService`、`VLMService`、`OCRPipeline`
- `deps.py` 以 module-level 變數保存 singleton，提供 `get_craft()`、`get_vlm()`、`get_pipeline()` 給 `Depends()`
- 服務生命週期：應用啟動時建立 → 請求間共享 → 應用關閉時清理

#### 任務狀態管理

- **角點流程**：`_pending_images: dict[str, np.ndarray]`（`corner.py` 內 dict 暫存）
- **OCR 流程**：`_tasks: Dict[str, dict]`（`ocr.py` 內 dict 暫存）
- ⚠️ 兩者均為 **in-memory**，**重啟即遺失**，生產環境建議改為 Redis

### 3.3 Services 層

#### CRAFTService (`services/craft_service.py`)

- **用途**：將 CRAFT 文字偵測包裝為線程安全的批次推論服務
- **模式**：背景 worker thread + Queue，batch_size=8, timeout=0.1s
- **關鍵方法**：
  - `start()` / `stop()`：啟動/停止 worker
  - `detect(image) → CRAFTResult`：提交單張圖片，阻塞等結果
- **注意**：CRAFT 模型載入於 GPU，記憶體約 1-2 GB

#### VLMService (`services/vlm_service.py`)

- **用途**：VLM 文字辨識，支援 3 個後端（策略模式）
- **建構**：`VLMService.from_settings(vlm_settings)` 工廠方法
- **後端切換**：`VLM_BACKEND` 環境變數（`vllm` / `gemini` / `openai`）
- **關鍵方法**：`recognize(image_b64, prompt) → str`
- **API 呼叫格式**：所有後端統一透過 OpenAI Chat Completions 格式

#### OCRPipeline (`services/ocr_pipeline.py`)

- **用途**：端到端 OCR 編排器
- **`run()` 方法簽章**：`run(pil_img, auto_rotate, remove_print, auto_split, on_progress=None)`
  - `on_progress`: `Callable[[str, float], None]` — 各階段回調，參數為 `(stage_name, progress_0_to_1)`
- **Pipeline 階段與進度廣播**：

  | 階段 | 進度值 | stage 名稱 |
  |---|---|---|
  | CRAFT 文字偵測 | 0.10 | `"偵測文字區塊"` |
  | 傾斜校正 | 0.25 | `"校正傾斜"` |
  | 印刷移除 | 0.40 | `"移除印刷文字"` |
  | 格線提取 | 0.55 | `"提取格線結構"` |
  | 直排→橫排 | 0.65 | `"重新格式化版面"` |
  | VLM 辨識（每列） | 0.65–0.95 | `"辨識第 N 欄"` |
  | 完成 | 1.00 | `"完成"` |

- **進度橋接**：`ocr.py` 使用 `asyncio.get_event_loop().run_coroutine_threadsafe()` 從 executor 線程安全地呼叫 async `broadcast_progress()`

### 3.4 Core 層（影像處理模組）

| 模組 | 職責 | 關鍵函式/類別 |
|---|---|---|
| `perspective.py` | 角點偵測 + 透視變換 | `Corners` dataclass, `detect_corners(img)`, `warp_perspective(img, corners)` |
| `craft_detector.py` | CRAFT 偵測結果封裝 | `CRAFTResult` (immutable dataclass), `run_craft(model, image)` |
| `grid_extractor.py` | 投影法格線發現 | `extract_grid(boxes, img_shape) → GridResult` |
| `rotation.py` | 多方法傾斜矯正 | `estimate_angle(boxes)`, `correct_rotation(img, boxes)` |
| `print_removal.py` | 印刷文字分類移除 | `classify_print_handwritten(boxes)`, `remove_print_region(img, boxes)` |
| `text_reformat.py` | 直→橫轉換 + 空白格偵測 | `reformat_columns()`, `_is_blank_cell()`, `refine_text_raw()` |
| `image_utils.py` | 格式轉換 + 分割 | `pil_to_bgr()`, `bgr_to_pil()`, `split_wide_image()` |

#### text_reformat.py 空白格偵測設計

`TextReformatConfig` 已從 18 個參數精簡為 4 個：

```python
@dataclass(frozen=True)
class TextReformatConfig:
    spacing: int = 20               # 輸出圖片字符間距（像素）
    binary_threshold: int = 128     # 二值化閾值
    blank_ink_ratio: float = 0.04   # 填充率低於此值視為稀疏墨水
    heat_rescue_peak: float = 0.40  # 熱圖峰值高於此值→確定是字符
```

其餘閾值為硬編碼模組常數（`_LINE_THICKNESS_RATIO`、`_LINE_SPAN_RATIO` 等）。

`_is_blank_cell()` 採用優先級決策樹：
1. 熱圖峰值 ≥ 0.40 → 確定是字符（最高優先，不再做其他判斷）
2. 填充率 = 0 → 空白
3. 線條形狀（細長橫/縱線）→ 若熱圖 active_ratio ≥ 0.03 才保留（防止誤刪「一」字），否則為格線空白
4. 稀疏墨水（fill ≤ 0.04）→ 有熱圖但無信號為雜訊（空白）；無熱圖則保留
5. 有意義墨水 → 非空白

**設計重點**：線條檢測的 rescue 邏輯獨立於全局 rescue，印刷格線（heat_active < 3%）不會被誤救回。

### 3.5 設定系統

**檔案**：`config/settings.py`

- 使用 Pydantic Settings v2，支援 `.env` 檔 + 環境變數
- **嵌套前綴規則**：`env_nested_delimiter="__"`，例如 `VLM__VLLM_BASE_URL=...`
- **結構**：

```python
Settings                    # 根設定
├── cuda_device: str        # GPU 設備（預設 "cuda:7"，部署時覆蓋為 "cuda:0"）
├── craft: CRAFTSettings    # CRAFT 模型參數
├── vlm: VLMSettings        # VLM 後端選項
├── pipeline: OCRPipelineSettings  # OCR 流程參數（含 4 個 reformat_* 欄位）
├── server: ServerSettings  # Web 服務器設定
├── log_level / log_format  # 日誌設定
```

- **取用方式**：`from config.settings import get_settings; s = get_settings()` — Singleton

---

## 4. 前端模組導覽

### 4.1 目錄結構

```
frontend/src/
├── App.tsx                 # 根組件 + 路由定義
├── main.tsx                # React DOM 入口
├── index.css               # 全域樣式（Tailwind + 漸層背景）
├── components/
│   ├── Layout.tsx          # 全局佈局：導航列 + 主內容區
│   ├── ImageDropzone.tsx   # 拖放上傳組件
│   ├── CornerEditor.tsx    # Konva Canvas 角點編輯器（含放大鏡）
│   ├── ManuscriptView.tsx  # RTL 稿紙網格渲染器
│   ├── ProgressBar.tsx     # 進度條（shimmer 動畫 + stage 標籤）
│   └── ZoomableImage.tsx   # 可縮放/拖曳圖片檢視器
├── hooks/
│   └── useOCRProgress.ts   # WebSocket + 輪詢狀態管理 Hook
├── lib/
│   ├── api.ts              # REST/WS API 客戶端
│   └── types.ts            # TypeScript 型別（映射 backend schemas）
└── pages/
    ├── UploadPage.tsx      # 上傳 → 角點 → 提交流程（帶連接線步驟指示器）
    └── ResultPage.tsx      # OCR 結果展示 + 即時進度（左右分欄）
```

### 4.2 路由

| 路徑 | 組件 | 功能 |
|---|---|---|
| `/` | `UploadPage` | 圖片上傳 → 角點互動編輯 → OCR 提交 |
| `/result` | `ResultPage` | 即時進度追蹤 + 結果顯示（線性/稿紙兩種視圖） |

### 4.3 頁面流程

#### UploadPage 三步驟（帶連接線步驟指示器）

```
Step 1: upload  ──── Step 2: corner  ──── Step 3: submitting
  ✓ 完成步驟顯示打勾圖示，連接線隨進度著色

Step 1: upload
└─ ImageDropzone 拖放或點擊選檔 → POST /corner/detect → 取得角點 + task_id

Step 2: corner
└─ CornerEditor 顯示 Canvas，使用者拖曳 4 角點微調
   ├─ 「確認校正」→ POST /corner/correct → OCR
   └─ 「跳過」→ 直接 POST /ocr/upload

Step 3: submitting
└─ POST /ocr/upload → navigate("/result?taskId=xxx")
```

#### ResultPage

- `useOCRProgress(taskId)` 同時開啟 WebSocket（即時進度）+ REST 輪詢（2s 間隔）
- **WebSocket 收到 `completed` / `failed` 時立即觸發最終一次 poll**，無需等待下一個輪詢週期
- 左欄：`ZoomableImage`（原始圖像，支援縮放拖曳）；右欄：辨識文字
- 完成後顯示：標題 + 文字（線性視圖）或 ManuscriptView（稿紙視圖）
- 「複製文字」按鈕：標題 + 本文一鍵複製到剪貼簿，有動畫反饋

### 4.4 關鍵組件

#### ZoomableImage（新增）

- **用途**：結果頁面原始圖像的互動式瀏覽器
- **功能**：
  - 滾輪縮放（以游標位置為中心，0.25×～10×）
  - 滑鼠拖曳 / 單指觸控平移
  - 右下角縮放按鈕（+/−/↺重置）與比例顯示
  - 拖曳邊界 clamp：確保圖片永遠至少有 60px 與容器重疊，不會完全消失
  - `wheel` 事件以 `{ passive: false }` 原生掛載，防止縮放時觸發頁面滾動

#### CornerEditor

- 使用 **Konva**（react-konva）繪製 Canvas
- 4 個可拖曳角點圓圈（TL:紅 / TR:橙 / BR:綠 / BL:藍）
- 拖曳時顯示 140×140px **放大鏡**（2.4x zoom + 十字線）
- 多邊形虛線連接 4 角點
- 自動縮放至視窗 82% 高度或最大 980px

#### ManuscriptView

- 渲染傳統中文直排稿紙格線
- 使用 `dir="rtl"` 實現由右至左欄位排列
- 每格 36px，支援 spacing_indexes 標記間距
- 欄位 0 = 最右欄（第一寫欄）

#### ProgressBar

- 0% 時顯示 shimmer 掃光動畫 + spinner stage 標籤
- 有進度時顯示 indigo → blue 漸層填充條

### 4.5 狀態管理

- **頁面級**：`useState`（UploadPage 步驟狀態、ResultPage 視圖切換）
- **Hook 級**：`useOCRProgress` 內部 state（進度、WebSocket 連線）
- **路由級**：React Router query params（`taskId`）+ location state（傳遞圖片預覽）
- 無全域狀態管理庫（Redux / Zustand 等）

### 4.6 API 客戶端

所有後端呼叫集中在 `lib/api.ts`：

| 函式 | 方法 | 端點 |
|---|---|---|
| `fetchHealth()` | GET | `/api/v1/health` |
| `detectCorners(file)` | POST | `/api/v1/corner/detect` |
| `correctCorners(req)` | POST | `/api/v1/corner/correct` |
| `submitOCR(file, opts)` | POST | `/api/v1/ocr/upload` |
| `pollOCRStatus(taskId)` | GET | `/api/v1/ocr/{taskId}` |
| `connectProgressWS(taskId)` | WS | `/api/v1/ws/{taskId}` |

---

## 5. 環境設定與部署

### 5.1 本地手動開發

```bash
# 後端
cd backend
cp .env.example .env    # 編輯 .env 填入設定
pip install -e ".[dev]"
uvicorn api.app:app --host 127.0.0.1 --port 8080 --reload

# 如需本地 vLLM
vllm serve Qwen/Qwen3-VL-2B-Instruct --port 8001 --tensor-parallel-size 1 --max-model-len 4096

# 前端
cd frontend
npm install
npm run dev    # Vite 開發伺服器 http://localhost:5173，/api 代理到 8080
```

> **注意**：`vite.config.ts` 啟用了 `server.watch.usePolling: true`（300ms 間隔），用於解決容器環境的 `ENOSPC: inotify watch limit reached` 問題。

### 5.2 Docker Compose

```bash
cp backend/.env.example backend/.env   # 編輯設定
docker compose up --build -d

# 常用指令
docker compose logs -f              # 查看即時日誌
docker compose restart backend      # 重啟單一服務
docker compose down                 # 停止（保留模型快取）
```

### 5.3 環境變數完整表

#### GPU & 通用

| 變數 | 預設值 | 說明 |
|---|---|---|
| `CUDA_DEVICE` | `cuda:0` | 推論 GPU 裝置 |
| `LOG_LEVEL` | `INFO` | 日誌等級 |

#### CRAFT 模型

| 變數 | 預設值 | 說明 |
|---|---|---|
| `CRAFT__LANGUAGES` | `["ch_tra"]` | CRAFT 偵測語言 |
| `CRAFT__CANVAS_SIZE` | `2560` | 偵測畫布大小 |
| `CRAFT__BATCH_SIZE` | `8` | 批次推論大小 |
| `CRAFT__BATCH_TIMEOUT` | `0.1` | 批次等待時限（秒） |

#### VLM 後端

| 變數 | 預設值 | 說明 |
|---|---|---|
| `VLM__BACKEND` | `vllm` | 後端選擇：`vllm` / `gemini` / `openai` |
| `VLM__VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM 端點 |
| `VLM__VLLM_API_KEY` | `EMPTY` | vLLM API 金鑰 |
| `VLM__VLLM_MODEL_NAME` | `Qwen/Qwen3-VL-2B-Instruct` | vLLM 模型名稱 |
| `VLM__GEMINI_API_KEY` | （空） | Gemini API 金鑰 |
| `VLM__GEMINI_MODEL_NAME` | `gemini-2.0-flash` | Gemini 模型 |
| `VLM__OPENAI_API_KEY` | （空） | OpenAI API 金鑰 |
| `VLM__OPENAI_MODEL_NAME` | `gpt-4o` | OpenAI 模型 |

#### OCR Pipeline

| 變數 | 預設值 | 說明 |
|---|---|---|
| `PIPELINE__AUTO_ROTATE` | `true` | 啟用傾斜校正 |
| `PIPELINE__REMOVE_PRINT` | `true` | 移除印刷文字 |
| `PIPELINE__AUTO_SPLIT` | `true` | 寬圖自動分割 |
| `PIPELINE__MAX_WORKERS` | `4` | VLM 並行辨識執行緒 |
| `PIPELINE__TIMEOUT` | `120` | 單次 OCR 超時（秒） |
| `PIPELINE__DEBUG_ENABLED` | `false` | 儲存中間處理圖片 |
| `PIPELINE__DEBUG_DIR` | `./debug/ocr_pipeline` | Debug 圖片目錄 |
| `PIPELINE__REFORMAT_SPACING` | `20` | 輸出圖片字符間距（像素） |
| `PIPELINE__REFORMAT_BINARY_THRESHOLD` | `128` | 空白格二值化閾值 |
| `PIPELINE__REFORMAT_BLANK_INK_RATIO` | `0.04` | 稀疏墨水判定閾值 |
| `PIPELINE__REFORMAT_HEAT_RESCUE_PEAK` | `0.40` | 熱圖峰值確認字符閾值 |

#### Docker Compose 專用

| 變數 | 預設值 | 說明 |
|---|---|---|
| `VLLM_MODEL` | `Qwen/Qwen3-VL-2B-Instruct` | vLLM 載入的模型 |
| `HUGGING_FACE_HUB_TOKEN` | （空） | HuggingFace 授權 token |

---

## 6. 已知問題與技術債

| # | 類別 | 說明 | 影響程度 |
|---|---|---|---|
| 1 | ~~**進度回報**~~ | ✅ **已修復**：pipeline 各階段呼叫 `on_progress` callback → `broadcast_progress()`，WebSocket 進度條正常運作 | — |
| 2 | **任務佇列** | 原計畫使用 Redis + MQTT，目前使用 in-memory dict + asyncio executor。重啟遺失所有任務 | 中 |
| 3 | **角點暫存** | `corner.py` 的 `_pending_images` 為 in-memory dict，大量上傳會佔用記憶體，且重啟遺失 | 低 |
| 4 | **空白格熱圖鄰居干擾** | CRAFT heatmap 從鄰近字符擴散到空白格邊緣，可能輕微影響空白格偵測準確度（已分析，尚未套用中心裁切修復） | 低 |
| 5 | **Docker 未驗證** | `docker-compose.yml` 撰寫完成但未在乾淨環境驗證完整啟動流程 | 中 |
| 6 | **無 CI/CD** | 沒有 GitHub Actions 或任何自動化 pipeline | 中 |
| 7 | **CORS 全開** | `allow_origins=["*"]`，生產環境應限縮 | 低 |
| 8 | **GPU 記憶體** | vLLM + CRAFT 同機部署需足夠 VRAM（建議 ≥ 16 GB） | — |

---

## 7. 建議改善方向

以下按建議優先順序排列：

### 高優先

1. **任務持久化** — 將 `_tasks` 與 `_pending_images` 遷移至 Redis，解決重啟遺失問題
2. **Docker 驗證** — 在乾淨機器執行 `docker compose up --build`，修正可能的映像問題

### 中優先

3. **空白格熱圖修復** — 在 `_is_blank_cell()` 中改用格子中心 60% 區域做 heatmap 分析，避免鄰居字符 bleed-over 的影響
4. **CI/CD** — 加入 GitHub Actions：lint (ruff) → test (pytest) → build (docker)
5. **CORS 收窄** — 改為環境變數配置允許的 origins

### 低優先

6. **多使用者支援** — 當前為單機 in-memory，如需多人同時使用需加入 session / auth
7. **模型熱替換** — 支援運行時切換 VLM 模型而不重啟
8. **批次處理** — 支援多張圖片批次 OCR

---

## 8. 常見維護 SOP

### 8.1 更換 VLM 後端

1. 編輯 `backend/.env`，將 `VLM__BACKEND` 改為 `gemini` 或 `openai`
2. 填入對應 API 金鑰（`VLM__GEMINI_API_KEY` 或 `VLM__OPENAI_API_KEY`）
3. 重啟 backend

若要新增全新後端（如 Anthropic Claude）：
1. 在 `services/vlm_service.py` 中新增對應的 strategy class
2. 更新 `VLMService.from_settings()` 工廠方法
3. 在 `config/settings.py` 的 `VLMSettings` 新增設定

### 8.2 調整 OCR Pipeline 參數

- 所有參數在 `config/settings.py` 的 `OCRPipelineSettings` 中定義
- 透過環境變數覆蓋，前綴 `PIPELINE__`
- 可在 API 請求中逐次覆蓋：`auto_rotate`、`remove_print`、`auto_split`

### 8.3 新增 API 路由

1. 在 `backend/api/routes/` 建立新 `.py` 檔
2. 定義 `router = APIRouter(prefix="/xxx", tags=["xxx"])`
3. 在 `api/app.py` 的 `create_app()` 中 `app.include_router()`
4. 在 `api/schemas.py` 新增對應的 Pydantic model

### 8.4 修改前端元件

- 所有 API 呼叫集中在 `frontend/src/lib/api.ts`
- 型別定義在 `frontend/src/lib/types.ts`（需與 backend `schemas.py` 同步）
- 頁面流程在 `pages/UploadPage.tsx` 和 `pages/ResultPage.tsx`

### 8.5 開啟 Debug 模式

設定環境變數：

```bash
PIPELINE__DEBUG_ENABLED=true
PIPELINE__DEBUG_DIR=./debug/ocr_pipeline
```

每次 OCR 執行會將中間處理圖片存入指定目錄，便於除錯。

### 8.6 切換 GPU

```bash
CUDA_DEVICE=cuda:1   # 後端使用第 2 張 GPU
```

⚠️ `config/settings.py` 中預設值為 `cuda:7`（開發機器設定），部署時透過環境變數覆蓋。

---

## 9. 分支記錄

| 分支 | 狀態 | 說明 |
|---|---|---|
| `main` | 穩定基線 | — |
| `feat/websocket-progress` | 已推送 | WebSocket 進度廣播、text_reformat 精簡、前端現代化 |
| `feat/zoomable-image` | 已推送（當前） | ZoomableImage 元件、vite polling 模式 |

---

## 10. 聯絡與參考

- **原始開發者**：使用 `git log` 查看 commit 歷史
- **外部依賴文件**：
  - [FastAPI 文件](https://fastapi.tiangolo.com/)
  - [CRAFT 論文](https://arxiv.org/abs/1904.01941)（EasyOCR 內建）
  - [vLLM 文件](https://docs.vllm.ai/)
  - [Konva.js 文件](https://konvajs.org/)
- **其他文件**：
  - `README.md` — 快速開始指南
  - `LLM.txt` — 給 LLM Agent 的結構化 codebase 參考
