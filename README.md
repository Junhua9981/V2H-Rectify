# V2H-Rectify

> **直排轉橫排手寫中文 OCR 校正系統**

一個完整的 OCR 處理流程，用於從掃描文件中偵測、校正並轉錄繁體中文手寫文字。
系統使用 CRAFT 進行文字偵測，並使用可配置的 VLM 後端（vLLM / Gemini / OpenAI）進行文字辨識。
目前同時支援**單張 OCR**與**批量 OCR**流程。

---

## 功能特色

- **透視校正**：自動偵測稿紙四角點，可在 Canvas 上手動微調後執行透視校正
- **影像前處理**：傾斜校正、印刷文字移除
- **直排辨識**：CRAFT 偵測手寫文字後，切分欄位交由 VLM 逐欄辨識
- **即時進度**：WebSocket 推送各處理階段進度，前端進度條即時更新
- **批量處理**：最多 50 張一次上傳，支援逐張角點覆寫、整批進度追蹤與結果匯出
- **互動結果頁**：原始圖像支援縮放（0.25×–10×）/ 拖曳瀏覽，辨識文字可切換橫排或稿紙直書視圖

---

## 專案結構

```
V2H-Rectify/
├── backend/      # Python FastAPI 服務（單張/批量 OCR API + pipeline）
├── frontend/     # React + Vite 單頁應用（上傳、角點編輯、結果與批量流程）
├── HANDOVER.md   # 交接文件（維護導向）
└── LLM.txt       # 給 Coding Agent 的結構化參考
```

---

## 快速開始

### 手動啟動

#### 後端（不含 vLLM 本地部署）

```bash
cd backend
cp .env.example .env          # 填入 API 金鑰與 GPU 設定
pip install -e ".[dev]"
uvicorn api.app:app --host 127.0.0.1 --port 8080 --reload
```

<details>
  <summary>可參考的 vLLM 部署方法（示例）</summary>

  ```bash
  vllm serve Qwen/Qwen3.5-9B --port 8001 --tensor-parallel-size 1 --max-model-len 4096
  ```
</details>

#### 前端

```bash
cd frontend
npm install
npm run dev                   # 將 /api 代理到 http://localhost:8080
```

> **注意**：`vite.config.ts` 啟用了 `server.watch.usePolling: true`，用於解決容器環境的 inotify watch 限制問題。

### Docker（完整系統）

一次啟動 **vLLM + backend + frontend** 三個服務：

```bash
# 在專案根目錄執行
cp backend/.env.example backend/.env   # 填入必要設定（API 金鑰、GPU 等）
docker compose up --build -d
```

| 服務 | 對外 Port | 說明 |
|---|---|---|
| frontend | 3000 | React UI（nginx 靜態服務 + API proxy） |
| backend  | 8080 | FastAPI OCR API |
| vllm     | 8001 | OpenAI 相容推論伺服器 |

啟動後瀏覽 [http://localhost:3000](http://localhost:3000) 即可使用。

**常用指令：**

```bash
# 查看即時 log
docker compose logs -f

# 僅重啟特定服務
docker compose restart backend

# 停止並移除容器（保留 HuggingFace 模型快取）
docker compose down
```

**可選環境變數**（在根目錄建立 `.env` 覆蓋預設值）：

| 變數 | 預設值 | 說明 |
|---|---|---|
| `VLLM_MODEL` | `Qwen/Qwen3.5-9B` | vLLM 載入的模型（示例） |
| `CUDA_DEVICE` | `cuda:0` | backend 推論裝置 |
| `HUGGING_FACE_HUB_TOKEN` | （空） | 下載需授權 HF 模型時填入 |

> **注意：** vLLM 首次啟動需下載模型，backend 會等待 vLLM 健康檢查通過後再啟動，請耐心等候。模型檔案快取於 Docker volume `huggingface_cache`，重啟後不需重新下載。

---

## 設定

所有後端設定都在 `backend/.env`（從 `backend/.env.example` 複製）：

| 變數               | 說明                           |
| ---------------- | ---------------------------- |
| `CUDA_DEVICE`    | 使用的 GPU，例如 `cuda:0`          |
| `VLM__BACKEND`   | `vllm` \| `gemini` \| `openai` |
| `VLM__VLLM_BASE_URL`  | vLLM 伺服器端點                   |
| `VLM__GEMINI_API_KEY` | Google Gemini API 金鑰         |
| `VLM__OPENAI_API_KEY` | OpenAI API 金鑰                |

---

## 前端路由

| 路徑 | 頁面 | 說明 |
|---|---|---|
| `/` | UploadPage | 單張上傳與角點校正 |
| `/result` | ResultPage | 單張進度與結果檢視 |
| `/batch` | BatchUploadPage | 批量上傳、信心檢視與角點調整 |
| `/batch/result` | BatchResultPage | 批量聚合進度、逐張結果、匯出 |

---

## API 一覽

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/api/v1/corner/detect` | 單張角點偵測 |
| POST | `/api/v1/corner/correct` | 單張透視校正 |
| POST | `/api/v1/ocr/upload` | 單張 OCR 提交 |
| GET | `/api/v1/ocr/{task_id}` | 單張 OCR 狀態/結果 |
| POST | `/api/v1/ocr/batch/prepare` | 批量角點預處理 |
| POST | `/api/v1/ocr/batch/submit` | 批量 OCR 提交 |
| GET | `/api/v1/ocr/batch/{batch_id}` | 批量 OCR 狀態/結果 |
| WS | `/api/v1/ws/{task_id}` | 單張進度推播 |
| WS | `/api/v1/ws/batch/{batch_id}` | 批量進度推播 |
| GET | `/api/v1/health` | 健康檢查（含 version） |

---

## OCR Pipeline 階段

後端 `OCRPipeline.run()` 的主要進度節點：

- `0.10`：偵測文字區塊
- `0.25`：校正傾斜
- `0.40`：移除印刷文字
- `0.55`：提取格線結構
- `0.65`：重新格式化版面
- `0.65-0.95`：辨識第 N 欄
- `1.00`：完成

---

## 技術棧

| 層級        | 技術                                       |
| --------- | ---------------------------------------- |
| 文字偵測      | CRAFT（透過 EasyOCR）                        |
| OCR / VLM | vLLM（可替換模型）或 Gemini / OpenAI API |
| 後端        | Python 3.10+, FastAPI, PyTorch, OpenCV   |
| 前端        | React 19, TypeScript, Vite 7, Tailwind CSS 4, Konva |
| 部署        | Docker Compose                           |

---

## 相關文件

| 文件 | 說明 |
|---|---|
| [HANDOVER.md](HANDOVER.md) | 完整交接文件 — 架構、模組導覽、部署、已知問題、維護 SOP |
| [LLM.txt](LLM.txt) | 給 LLM Agent 的結構化 codebase 參考 — 所有檔案/函式/API/設定的索引 |

---

## 已知缺陷

1. **任務無持久化**：`_tasks`、`_pending_images`、`_batches` 均為 in-memory，重啟會遺失。
2. **Docker 乾淨環境驗證不足**：compose 已可用，但仍建議在全新環境完整驗證。
3. **測試覆蓋不完整**：目前以 `text_reformat`（9 個測試）為主，其餘模組測試尚待補強。
4. **CORS 全開**：`allow_origins=["*"]`，生產環境應改為白名單。
5. **批量回應檔名欄位待補**：`/ocr/batch/submit` 回傳的 task `filename` 目前為空字串。

---

## 版本

- 後端 `FastAPI version`：`3.0.0`
- `GET /api/v1/health` 的 `version`：`3.0.0`
