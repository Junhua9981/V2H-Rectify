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

### 後端

```bash
cd backend
cp .env.example .env          # 填入你的 API 金鑰與 GPU 設定
pip install -e ".[dev]"
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
````

### 前端

```bash
cd frontend
npm install
npm run dev                   # 將 /api 代理到 http://localhost:8080
```

### Docker（完整系統）

```bash
cd backend
cp .env.example .env
docker compose up --build
```

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


## 小缺陷
1. 識別中的進度條雖然存在，也有websocket可以獲取當前狀態，但實際上現在是使用 `/ocr/{taskid}` 的API進行polling，且不會分段回傳，導致進度條實際上沒有作用
2. 本來後端要使用redis與mqtt(之類的)進行任務的排成推送，但在用量沒有很大或需要分離部署的情況沒有將其完成，當前使用較為簡單的asyncio evenloop來完成
3. 前端有點醜
4. Docker未進行嘗試，但應該可用