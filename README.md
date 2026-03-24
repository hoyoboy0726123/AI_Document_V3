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
- Ollama（啟用 LLM / Embedding / Vision 功能必須安裝）

Linux / WSL 建議先安裝：
- `build-essential`
- `python3-dev`
- `libglib2.0-0`
- `libsm6`
- `libxrender1`
- `libxext6`

---

## 0. 安裝 Ollama（必要前置步驟）

本系統的 LLM 問答、向量嵌入、VL 圖片分析均依賴 Ollama，**請在啟動本專案前先完成安裝**。

### 下載 Ollama

前往官網下載對應平台的安裝包：

**https://ollama.com/download**

| 平台 | 安裝方式 |
|------|---------|
| macOS | 下載 `.dmg` 安裝，完成後 Ollama 會常駐在選單列 |
| Windows | 下載 `.exe` 安裝程式，完成後 Ollama 會常駐在系統匣 |
| Linux | 執行一鍵安裝指令（見下方） |

**Linux 一鍵安裝：**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 確認 Ollama 正常運行

```bash
ollama --version
```

### 下載所需模型

```bash
ollama pull qwen3:8b           # LLM（問答 / 摘要）
ollama pull qwen2.5vl:7b       # 視覺模型（PDF 圖片分析）
ollama pull qwen3-embedding:8b # 向量嵌入（語意搜尋）
```

> 首次下載需要一段時間，依網路速度與模型大小而定（合計約 15–20 GB）。

### 確認模型已就緒

```bash
ollama list
```

看到三個模型都在清單中即可繼續下一步。

---

## 1. 下載專案

```bash
git clone https://github.com/hoyoboy0726123/AI_Document_V3.git
cd AI_Document_V3
```

---

## 2. 先理解啟動方式（很重要）

這個專案目前是 **前後端分離架構**：

- `backend/`：FastAPI API + OCR + RAG 邏輯
- `frontend/`：React / Vite 使用者介面

### 本機開發模式
如果你用原生方式啟動，通常需要 **兩個終端機**：

- 終端機 1：啟動 backend
- 終端機 2：啟動 frontend

### 容器模式
如果你使用 Docker Compose：

```bash
docker compose up --build
```

雖然底層還是 frontend + backend 兩個服務，
但你不需要自己手動開兩個 terminal 管理。

### Ollama 建議部署方式
目前最建議的方式是：

- frontend：本機或容器
- backend：本機或容器
- **Ollama：跑在宿主機（host machine）**

也就是說，**不要先急著把 Ollama 包進 compose**，先讓它直接安裝在你的電腦上會比較穩定、也比較容易除錯。

---

## 3. 安裝 backend 依賴

提供兩種方式，擇一即可：

### 方式 A：uv（推薦）

`uv` 速度快、自動管理虛擬環境，推薦第一次使用本專案的人優先選這種方式。

若還沒安裝 uv：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安裝依賴：

```bash
cd backend
uv sync
```

啟用虛擬環境（可選，uv run 會自動使用）：

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 方式 B：pip

若你不想裝 uv，也可以用標準的 pip 方式：

```bash
cd backend
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

> 注意：`requirements.txt` 若不存在，可從 `pyproject.toml` 匯出：
> ```bash
> pip install uv
> uv export --no-hashes -o requirements.txt
> ```

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
ollama pull qwen3:8b
ollama pull qwen2.5vl:7b
ollama pull qwen3-embedding:8b
```

預設 `.env`：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_LLM_MODEL=qwen3:8b
OLLAMA_VISION_MODEL=qwen2.5vl:7b
OLLAMA_EMBED_MODEL=qwen3-embedding:8b
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

### Backend（uv）

```bash
cd backend
uv sync
cp .env_example .env   # 再編輯 .env
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Backend（pip）

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env_example .env        # 再編輯 .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker（最快）

```bash
cp backend/.env_example backend/.env   # 再編輯 .env
docker compose up --build
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

## 11. 容器 / Docker 安裝方式

如果你想在另一台電腦快速部署，也可以直接走容器方式。

### 我建議的部署組合

目前最推薦的是這個組合：

- **frontend：容器**
- **backend：容器**
- **Ollama：宿主機安裝（不要先容器化）**

這樣做的好處是：
- 比較容易安裝與除錯
- 比較不容易卡在 GPU / 網路 / volume 問題
- 未來要改模型或檢查 Ollama 狀態也比較直覺

如果你是：
- **macOS**：很建議用這個模式
- **Windows + WSL**：也建議先走這個模式
- **Linux**：也可以用這個模式當第一版部署

### 先安裝 Docker

請先安裝：
- Docker Desktop（Windows / macOS）
- 或 Docker Engine + Docker Compose Plugin（Linux）

安裝完成後先確認：

```bash
docker --version
docker compose version
```

### 啟動方式

專案根目錄已補上：
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

### 停止容器

```bash
docker compose down
```

### 重新建置

```bash
docker compose up --build
```

### 注意事項

1. 目前 compose 先包含：
   - frontend
   - backend

2. **Ollama 目前建議直接安裝在宿主機**，不要先放進 compose。

3. 若 backend 在容器內，但 Ollama 在宿主機，`OLLAMA_BASE_URL` 不要直接寫 `127.0.0.1`，因為那會指向容器自己。

#### macOS / Windows Docker Desktop
通常可用：

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

#### Linux
通常要改成宿主機的實際 IP，例如：

```env
OLLAMA_BASE_URL=http://192.168.1.100:11434
```

4. 如果你只是想先把整個專案跑起來，建議順序是：
   - 先安裝並確認宿主機上的 Ollama 可用
   - 再用 `docker compose up --build` 啟動 frontend + backend
   - 最後再測試 OCR / embedding / RAG

---

## 12. Docker 安裝補充（Ubuntu / Linux）

若你是在 Ubuntu / Linux 安裝 Docker，可參考以下基本流程：

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

驗證：

```bash
docker --version
docker compose version
```

若想避免每次都加 `sudo`：

```bash
sudo usermod -aG docker $USER
newgrp docker
```

---

## 13. macOS 安裝建議

macOS 原則上可以跑，而且我更建議這樣做：

- Docker Desktop 跑 frontend + backend
- Ollama 直接安裝在 macOS 宿主機

### 建議流程

1. 安裝 Docker Desktop
2. 安裝 Ollama（宿主機）
3. 先在宿主機確認 Ollama 正常
4. clone 專案
5. 複製 `backend/.env_example` 成 `backend/.env`
6. 將 `OLLAMA_BASE_URL` 設成：

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

7. 啟動：

```bash
docker compose up --build
```

這樣通常是最省事的 macOS 跑法。

---

## 14. Windows 安裝建議

如果你是在 Windows 上部署，建議直接走：
- **Windows 原生安裝**
- 或 **Docker Desktop + 宿主機 Ollama**

### 建議做法 A：Docker Desktop（最推薦）

1. 安裝 Docker Desktop
2. 在 Windows 安裝 Ollama
3. clone 專案
4. 複製設定檔：

```powershell
copy backend\.env_example backend\.env
```

5. 編輯 `backend/.env`，將 Ollama 指向宿主機：

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

6. 啟動：

```powershell
docker compose up --build
```

### 建議做法 B：Windows 原生啟動

先安裝：
- Python 3.12
- Node.js 22
- uv
- Ollama

然後：

```powershell
git clone https://github.com/hoyoboy0726123/AI_Document_V3.git
cd AI_Document_V3
```

#### backend

```powershell
cd backend
copy .env_example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### frontend（另一個 terminal）

```powershell
cd frontend
npm install
npm run dev
```

### Windows 注意事項

- 如果 backend 跑在容器內，而 Ollama 跑在 Windows 宿主機，請優先使用：

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

- 如果 frontend / backend 都是 Windows 原生執行，通常可維持：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

---

## 15. 建議後續改善

- 補正式的 Alembic migration
- 補 Ollama service 版的 compose
- 補 CI 檢查
- 補更完整的 README 截圖與 API 文件

---

## 授權

若你要公開商用或對外發佈，建議補上正式 LICENSE。
