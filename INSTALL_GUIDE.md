# 安裝與啟動指南

以下流程說明如何在新的電腦上部署本專案（前後端 + Ollama）。若只需其中一部分，可視需求擷取使用。

---

## 1. 必備環境
- **Git**
- **Python 3.11+**（建議 64-bit）
- **Node.js 18+ 與 npm**
- **Ollama 0.1.34+**（需支援本地模型）
- **Visual C++ Build Tools / Xcode Command Line Tools**（依作業系統而定，用於編譯 Python 套件）

> Windows 建議全程使用 PowerShell；macOS / Linux 可改用 bash，指令只需將分號換成 `&&`。

---

## 2. 取得原始碼
```powershell
git clone <your-repo-url> AI_Document_V2
cd AI_Document_V2
```

---

## 3. Backend 安裝與設定
1. **建立虛擬環境並啟用**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate      # Windows
   # 或 source venv/bin/activate  # macOS / Linux
   ```

2. **安裝依賴**
   ```powershell
   pip install --upgrade pip
   pip install -r backend/requirements.txt
   ```

3. **建立環境變數檔**
   ```powershell
   Copy-Item backend/.env_example backend/.env
   # 編輯 backend/.env，填入 SECRET_KEY、資料庫路徑與 Ollama 相關設定
   ```
   - `OLLAMA_LLM_MODEL`：RAG / 一般對話用模型（預設 `qwen3:8b`）。
   - `OLLAMA_VISION_MODEL`：單頁/多頁 PDF 解析模型（預設 `qwen2.5vl:7b`）。
   - `OLLAMA_EMBED_MODEL`：向量化模型（預設 `quentinz/bge-large-zh-v1.5:latest`）。
   - 若遇到 `time: missing unit in duration "-1"`，請清空 OS 層級的 `OLLAMA_KEEP_ALIVE` 環境變數後重新啟動終端。

4. **準備資料夾**
   ```powershell
   mkdir backend\storage\documents,backend\storage\tmp -Force
   ```

5. **啟動 Backend**
   ```powershell
   cd backend
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   - 伺服器啟動後可透過 `http://127.0.0.1:8000/docs` 檢查 API。

---

## 4. Frontend 安裝與啟動
1. **安裝依賴**
   ```powershell
   cd frontend
   npm install
   ```

2. **啟動開發伺服器**
   ```powershell
   npm run dev
   ```
   - 預設使用 `http://127.0.0.1:5173`。

3. **建置正式版（可選）**
   ```powershell
   npm run build
   npm run preview
   ```

---

## 5. Ollama 與模型
1. 安裝 Ollama → <https://www.ollama.com/download>
2. 啟動 Ollama service（安裝後預設常駐 `127.0.0.1:11434`）。
3. 下載所需模型（依 `.env` 設定，以下為預設）
   ```powershell
   ollama pull qwen3:8b
   ollama pull qwen2.5vl:7b
   ollama pull quentinz/bge-large-zh-v1.5:latest
   ```
4. 可用 `ollama list` 檢查模型是否成功下載。

---

## 6. 常見啟動指令總覽
| 作業 | 指令 (PowerShell) |
| --- | --- |
| 啟用 venv | `.\venv\Scripts\Activate` |
| Backend 啟動 | `cd backend; uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` |
| Frontend dev | `cd frontend; npm run dev` |
| Frontend build | `cd frontend; npm run build` |
| 清除 Ollama KeepAlive | `[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE',$null,'User')` |

---

## 7. 驗證流程
1. 確認 Ollama API 正常：`Invoke-WebRequest http://127.0.0.1:11434/api/version`（或 `curl`）。
2. Backend `/health` 或 `/docs` 能回應。
3. 前端 UI 能登入並操作 PDF 單/多頁分析與 RAG 查詢。若多頁分析出現錯誤，確認選取頁數 ≤10 並檢查後端日誌。

---

## 8. 其他注意事項
- 若部署在 macOS/Linux，請將路徑分隔符改為 `/`，並使用 `source venv/bin/activate`。
- 在新機移植後記得同步資料庫或重新建立 FAISS 索引。可透過管理介面的「清除向量」按鈕重新向量化。
- 如需於 Docker / 雲端部署，請另行撰寫適合的 compose / service 檔，並確保 Ollama 端點可被後端存取。

祝順利完成部署！
