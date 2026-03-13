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

## 10. 一鍵安裝腳本

專案根目錄已補上 `setup.sh`：

```bash
chmod +x setup.sh
./setup.sh
```

它會幫你：
- 檢查 `python3` / `npm` / `uv`
- 在 `backend/` 執行 `uv sync`
- 在 `frontend/` 執行 `npm install`
- 如果 `backend/.env` 不存在，會自動從 `.env_example` 複製一份

---

## 11. Docker Compose

如果你想快速在另一台電腦把前後端一起拉起來，專案根目錄已補上：
- `docker-compose.yml`

用法：

```bash
cd AI_Document_V3
cp backend/.env_example backend/.env
# 編輯 backend/.env

docker compose up --build
```

啟動後：
- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`

> 目前 compose 先包含 frontend + backend。
> Ollama 仍建議安裝在宿主機，或之後再另外補成獨立服務。

---

## 12. Windows / WSL 安裝建議

如果你是在 Windows 上部署，建議走：
- **Windows 11 + WSL2 + Ubuntu**

### 步驟摘要

1. 安裝 WSL2
```powershell
wsl --install
```

2. 進入 Ubuntu 後安裝基礎工具
```bash
sudo apt update
sudo apt install -y curl git build-essential python3 python3-dev python3-pip npm
```

3. 安裝 uv
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

4. clone 專案
```bash
git clone https://github.com/hoyoboy0726123/AI_Document_V3.git
cd AI_Document_V3
```

5. 執行一鍵安裝
```bash
./setup.sh
```

6. 啟動 backend
```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

7. 啟動 frontend
```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

### WSL 注意事項

- 若 Ollama 裝在 Windows 而 backend 跑在 WSL，`OLLAMA_BASE_URL` 可能不能直接用 `127.0.0.1`
- 你可能需要改成 Windows 主機 IP，例如：

```env
OLLAMA_BASE_URL=http://<windows-host-ip>:11434
```

- 如果你是全部都裝在 WSL，那就維持：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

---

## 13. 建議後續改善

- 補正式的 Alembic migration
- 補 Ollama service 版的 compose
- 補 CI 檢查
- 補更完整的 README 截圖與 API 文件

---

## 授權

若你要公開商用或對外發佈，建議補上正式 LICENSE。
