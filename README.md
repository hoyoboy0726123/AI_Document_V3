# AI_Document_V3

AI_Document_V3 是一個文件管理 + OCR + RAG 問答專案，前端使用 React/Vite，後端使用 FastAPI。

目前已驗證的重點：
- 一般文字型 PDF 匯入流程可用
- 圖片型 PDF 可走 PaddleOCR 路徑
- OCR / chunking / DB 落庫主流程已打通

---

## 專案結構

```text
AI_Document_V3/
├─ frontend/   # React + Vite 前端
├─ backend/    # FastAPI + SQLite + OCR + RAG 後端
└─ README.md
```

---

## 系統需求

建議環境：
- Python 3.12
- Node.js 20+（建議 22）
- npm
- [uv](https://docs.astral.sh/uv/)
- Ollama（如果要啟用 embedding / LLM / vision）

Linux / WSL 建議先安裝：
- `build-essential`
- `python3-dev`
- `libglib2.0-0`
- `libsm6`
- `libxrender1`
- `libxext6`

---

## 1. 下載專案

```bash
git clone https://github.com/hoyoboy0726123/AI_Document_V3.git
cd AI_Document_V3
```

---

## 2. 用 uv 安裝 backend

`backend/` 已補上 `pyproject.toml`，可以直接用 `uv` 建立虛擬環境與安裝依賴。

```bash
cd backend
uv sync
```

如果你的機器還沒裝 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 啟用虛擬環境

Linux / macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

---

## 3. 設定 backend 環境變數

複製範本：

```bash
cp .env_example .env
```

至少要修改：

```env
SECRET_KEY=換成你自己的長隨機字串
```

如果要啟用完整 RAG / LLM / embedding 功能，也要先準備 Ollama：

```bash
ollama pull llama3.2
ollama pull llava
ollama pull all-minilm
```

預設 `.env`：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_VISION_MODEL=llava
OLLAMA_EMBED_MODEL=all-minilm
```

---

## 4. 啟動 backend

在 `backend/` 目錄下：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康檢查：

```bash
curl http://127.0.0.1:8000/health
```

---

## 5. 安裝與啟動 frontend

另開一個 terminal：

```bash
cd frontend
npm install
npm run dev
```

前端預設會跑在：
- `http://127.0.0.1:3000`

---

## 6. 第一次登入

後端啟動後會自動建立預設管理員（若 `.env` 未改）：

- Username: `admin`
- Password: `Admin@123`

**建議第一次登入後立刻改密碼。**

---

## 7. OCR 說明

### 文字型 PDF
會優先走 `pdfminer.six` 做文字擷取。

### 圖片型 PDF
會走 PaddleOCR。

目前專案已做的相容性修正：
- PaddleOCR 3.4.0 改讀 `rec_texts` / `rec_scores`
- 圖片輸入改為 `numpy.ndarray`
- CPU 路徑預設停用 MKL-DNN（`enable_mkldnn=False`），避免特定環境下的 runtime 問題

### 注意
`paddlepaddle` 已列入依賴，預設是 CPU 版。
如果之後你要改成 GPU 版（例如 NVIDIA 5090），建議先確認 CPU 路徑穩定，再另外依 Paddle 官方文件切換成對應的 GPU wheel。

---

## 8. 目前已知限制

1. 若 Ollama 沒啟動：
   - 文件上傳 / OCR / chunking / DB 落庫仍可工作
   - 但 embedding / RAG 問答不會完整可用

2. PaddleOCR 第一次執行時會下載模型：
   - 首次啟動較慢屬正常現象

3. 目前預設資料庫是 SQLite：
   - 適合開發與單機使用

---

## 9. 快速安裝摘要

### Backend

```bash
cd backend
uv sync
cp .env_example .env
# 編輯 .env
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## 10. 建議後續改善

- 補正式的 Alembic migration
- 補 docker-compose（backend + frontend + ollama）
- 補 CI 檢查
- 補更完整的 README 截圖與 API 文件

---

## 授權

若你要公開商用或對外發佈，建議補上正式 LICENSE。
