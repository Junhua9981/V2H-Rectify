# V2H-Rectify

> **直排轉橫排手寫中文 OCR 校正系統**

一個完整的 OCR 處理流程，用於從掃描文件中偵測、校正並轉錄繁體中文手寫文字。  
系統使用 CRAFT 進行文字偵測，並使用可配置的 VLM 後端（vLLM / Gemini / OpenAI）進行文字辨識。

---

## 專案結構

```
V2H-Rectify/
├── backend/      # Python FastAPI 服務（CRAFT 偵測器 + OCR 處理流程）
└── frontend/     # React + Vite 單頁應用（圖片上傳、標註、結果顯示）

````

---

## 快速開始

### 手動啟動

#### 後端 (不包含 vLLM 等本地模型部署)

```bash
cd backend
cp .env.example .env          # 填入你的 API 金鑰與 GPU 設定
pip install -e ".[dev]"
uvicorn api.app:app --host 127.0.0.1 --port 8080 --reload
```

<details>
  <summary>可參考的 vLLM 部署方法</summary>

  ```bash
  vllm serve Qwen/Qwen3-VL-2B-Instruct --port 8001 --tensor-parallel-size 1 --max-model-len 4096
  ```
</details>

#### 前端

```bash
cd frontend
npm install
npm run dev                   # 將 /api 代理到 http://localhost:8080
```

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
| `VLLM_MODEL` | `Qwen/Qwen3-VL-2B-Instruct` | vLLM 載入的模型 |
| `CUDA_DEVICE` | `cuda:0` | backend 推論裝置 |
| `HUGGING_FACE_HUB_TOKEN` | （空） | 下載需授權 HF 模型時填入 |

> **注意：** vLLM 首次啟動需下載模型，backend 會等待 vLLM 健康檢查通過後再啟動，請耐心等候。模型檔案快取於 Docker volume `huggingface_cache`，重啟後不需重新下載。

---

## 設定

所有後端設定都在 `backend/.env`（從 `backend/.env.example` 複製）：

| 變數               | 說明                           |
| ---------------- | ---------------------------- |
| `CUDA_DEVICE`    | 使用的 GPU，例如 `cuda:0`          |
| `VLM_BACKEND`    | `vllm` | `gemini` | `openai` |
| `VLLM_BASE_URL`  | vLLM 伺服器端點                   |
| `GEMINI_API_KEY` | Google Gemini API 金鑰         |
| `OPENAI_API_KEY` | OpenAI API 金鑰                |

---

## 技術棧

| 層級        | 技術                                       |
| --------- | ---------------------------------------- |
| 文字偵測      | CRAFT（透過 EasyOCR）                        |
| OCR / VLM | Qwen2.5-VL(vLLM部屬) 也可用 gemini / openai api等  |
| 後端        | Python 3.10+, FastAPI, PyTorch           |
| 前端        | React 19, TypeScript, Vite, Tailwind CSS |
| 部署        | Docker Compose                           |


## 相關文件

| 文件 | 說明 |
|---|---|
| [HANDOVER.md](HANDOVER.md) | 完整交接文件 — 架構、模組導覽、部署、已知問題、維護 SOP |
| [LLM.txt](LLM.txt) | 給 LLM Agent 的結構化 codebase 參考 — 所有檔案/函式/API/設定的索引 |

---

## 小缺陷
1. 識別中的進度條雖然存在，也有websocket可以獲取當前狀態，但實際上現在是使用 `/ocr/{taskid}` 的API進行polling，且不會分段回傳，導致進度條實際上沒有作用
2. 本來後端要使用redis與mqtt(之類的)進行任務的排成推送，但在用量沒有很大或需要分離部署的情況沒有將其完成，當前使用較為簡單的asyncio evenloop來完成
3. 前端有點醜
4. Docker 未驗證，本地部屬建議直接啟動即可
5. 沒做unit test