# V2H-Rectify

> **Vertical-to-Horizontal Handwritten Chinese OCR Rectification System**

A full-stack OCR pipeline that detects, rectifies, and transcribes traditional Chinese handwriting from scanned documents. The system uses CRAFT for text detection and a configurable VLM backend (vLLM / Gemini / OpenAI) for recognition.

---

## Repository Structure

```
V2H-Rectify/
├── backend/      # Python FastAPI service (CRAFT detector + OCR pipeline)
└── frontend/     # React + Vite SPA (image upload, annotation, results)
```

---

## Quick Start

### Backend

```bash
cd backend
cp .env.example .env          # fill in your API keys and GPU settings
pip install -e ".[dev]"
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev                   # proxies /api → http://localhost:8080
```

### Docker (full stack)

```bash
cd backend
cp .env.example .env
docker compose up --build
```

---

## Configuration

All backend settings are in `backend/.env` (copy from `backend/.env.example`):

| Variable | Description |
|---|---|
| `CUDA_DEVICE` | GPU to use, e.g. `cuda:0` |
| `VLM_BACKEND` | `vllm` \| `gemini` \| `openai` |
| `VLLM_BASE_URL` | vLLM server endpoint |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Text Detection | CRAFT (via EasyOCR) |
| OCR / VLM | Qwen2.5-VL / Gemini / GPT-4o |
| Backend | Python 3.10+, FastAPI, PyTorch |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Deployment | Docker Compose |
