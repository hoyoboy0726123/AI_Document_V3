# AI_Document_V3 使用說明書

本說明書適用於已完成安裝並成功啟動的使用者。若尚未安裝，請先閱讀 [README.md](./README.md)。

---

## 目錄

1. [系統概覽](#1-系統概覽)
2. [登入與帳號管理](#2-登入與帳號管理)
3. [文件管理](#3-文件管理)
4. [PDF 預覽與 VL 分析](#4-pdf-預覽與-vl-分析)
5. [RAG 問答（QA Console）](#5-rag-問答qa-console)
6. [我的筆記本](#6-我的筆記本)
7. [管理員功能](#7-管理員功能)
8. [Ollama 模型設定](#8-ollama-模型設定)
9. [環境變數參考](#9-環境變數參考)
10. [常見問題](#10-常見問題)

---

## 1. 系統概覽

AI_Document_V3 是一套本地部署的企業文件管理與智能問答系統，核心功能包含：

| 功能 | 說明 |
|------|------|
| 文件上傳與管理 | 支援文字型與圖片型 PDF，自動 OCR 與向量化 |
| VL 視覺模型分析 | 使用 qwen2.5vl 對 PDF 頁面進行深度圖文解析 |
| RAG 問答 | 基於向量搜尋的跨文件語意問答，支援多輪對話 |
| 個人筆記本 | 跨文件收藏重要 Q&A，支援 Markdown 筆記 |
| 權限控管 | 管理員 / 一般使用者兩層權限 |

所有資料（文件、對話紀錄、分析紀錄、筆記）均儲存於本地，不上傳至任何雲端服務。

---

## 2. 登入與帳號管理

### 首次登入

系統啟動後自動建立預設管理員帳號：

- **帳號**：`admin`
- **密碼**：`Admin@123`

> 建議第一次登入後立即至個人設定更改密碼。

### 權限說明

| 角色 | 可執行操作 |
|------|-----------|
| **管理員 (admin)** | 上傳、編輯、刪除文件；存取向量搜尋、向量健康、Metadata 管理頁面 |
| **一般使用者** | 瀏覽文件列表、PDF 預覽與 VL 分析、RAG 問答、筆記本 |

側邊欄選單會依據登入帳號的角色自動顯示或隱藏對應功能。

---

## 3. 文件管理

### 3.1 瀏覽文件列表

點選左側側邊欄「**文件管理**」進入文件列表，可：

- 以關鍵字搜尋文件標題
- 依分類、專案篩選
- 點選任一文件進入詳細頁

### 3.2 上傳文件（管理員）

點選左側側邊欄「**新增文件**」。

**上傳流程：**

1. 拖拉或點選上傳 PDF 檔案
2. 系統自動偵測文字量：
   - **文字量充足** → 直接進入 OCR + 向量化流程
   - **文字量不足（圖片型 PDF）** → 彈出選擇視窗

**圖片型 PDF 選項視窗：**

| 選項 | 說明 |
|------|------|
| **使用 VL 解析（推薦）** | 呼叫 qwen2.5vl 視覺模型，辨識圖片、圖表、表格與嵌入文字，完整向量化後可供問答搜尋 |
| **僅供預覽** | 不做 VL 解析，上傳後只能預覽 PDF，無法進行語意搜尋 |

> 圖片型 PDF 若選擇「僅供預覽」，後續可在文件詳細頁手動觸發重新向量化（管理員）。

### 3.3 編輯文件 Metadata（管理員）

進入文件詳細頁後，可編輯：

- 標題
- 分類（Classification）
- 專案（Project）
- 關鍵字
- 自訂 Metadata 欄位

系統提供 **AI 建議** 功能，點選「AI 建議」按鈕後，模型會根據文件內容自動填入建議值，使用者確認後套用。

### 3.4 刪除文件（管理員）

在文件詳細頁或文件列表中，點選刪除按鈕。刪除後向量索引也會同步清除。

---

## 4. PDF 預覽與 VL 分析

### 4.1 開啟 PDF 預覽

在文件列表點選任一文件，進入文件詳細頁後點選「**預覽 PDF**」按鈕，即可開啟 PDF 預覽 Modal。

### 4.2 單頁 VL 分析

在 PDF 預覽 Modal 中：

1. 瀏覽至目標頁面
2. 在「**分析此頁**」輸入欄輸入問題（或留空讓 AI 自動分析頁面重點）
3. 點選「**送出**」按鈕（不支援 Enter 送出，避免誤觸）

**留空時的輸出格式：**
- 頁面主題
- 圖片與圖表描述
- 文字內容
- 核心重點（3–5 條）

### 4.3 多頁 VL 分析

適用於需要理解連續頁面或整體章節的情境。

1. 在「**分析頁碼**」欄位輸入想分析的頁碼（例如：`1,2,3,4,5`）
2. 點選「**分析多頁**」

**系統上限**：單次最多可分析的頁數由 `.env` 的 `MAX_PDF_ANALYSIS_PAGES` 控制，前端會動態讀取並限制輸入。

**輸出格式（不輸入問題時）：**

```
## 整體主題
## 各頁重點
## 圖表與視覺資訊
## 跨頁關聯
## 核心重點摘要
```

**追問**：分析完成後，可在「**追問**」輸入欄輸入問題，模型會根據原始頁面圖片（所有頁面）跨頁回答。

### 4.4 分析紀錄

每位使用者的分析對話紀錄獨立儲存（不與其他使用者共享）。

- 重新開啟 PDF 預覽時，會自動載入該使用者的上次紀錄
- 點選「**清除紀錄**」可刪除該文件的個人分析歷史

---

## 5. RAG 問答（QA Console）

### 5.1 基本問答

點選左側「**問答**」進入 QA Console。

1. 在輸入欄輸入問題
2. 點選送出
3. 系統自動進行向量搜尋，找出最相關段落後由 LLM 生成回答
4. 回答下方顯示來源段落與頁碼，可點選直接跳至對應 PDF 頁面

### 5.2 多輪對話

QA Console 支援多輪對話，系統會自動分析：

- 當前問題是否為追問
- 若是追問，是否需要重新搜尋或沿用上一輪的向量結果
- 優化搜尋關鍵字（保留上一輪主題 + 新問題意圖）

對話紀錄儲存於資料庫，與個人帳號綁定，重新整理頁面後仍會保留。

點選「**清除對話**」可重置對話紀錄。

### 5.3 篩選搜尋範圍

可在問答前選擇：

- **全部文件**：搜尋所有已向量化的文件
- **指定分類 / 專案**：只搜尋特定類別的文件

### 5.4 AI 無法找到答案時

若向量搜尋結果不足，系統提供「**AI 自由回答**」模式，直接由 LLM 以通識知識回答（不依賴文件內容）。

---

## 6. 我的筆記本

點選左側「**我的筆記本**」。

### 6.1 新增筆記

在 QA Console 回答完後，點選「**儲存至筆記**」，即可將問答對儲存為一則筆記，自動帶入來源文件與頁碼連結。

### 6.2 瀏覽筆記

筆記本以卡片形式顯示，每張卡片包含：

- 問題標題
- 回答摘要（Markdown 渲染）
- 來源文件連結（點擊可直接跳至對應 PDF 頁面）
- 建立時間

### 6.3 點擊卡片查看完整內容

點選筆記卡片可開啟全文 Markdown 閱讀視窗。

### 6.4 刪除筆記

在筆記卡片上點選刪除按鈕。每位使用者只能看到和刪除自己的筆記。

---

## 7. 管理員功能

以下功能僅管理員帳號可見：

### 7.1 Metadata 管理

路徑：左側選單 → **Metadata 管理**

管理文件的分類（Classification）與專案（Project）標籤，包含：

- 新增 / 編輯 / 刪除分類標籤
- 新增 / 編輯 / 刪除專案標籤

### 7.2 向量搜尋測試

路徑：左側選單 → **向量搜尋**

輸入任意查詢文字，查看向量相似度搜尋結果，可用於：

- 確認文件是否已正確向量化
- 測試特定關鍵字的命中效果
- 調整搜尋參數（Top K、相似度閾值）

### 7.3 向量索引健康檢查

路徑：左側選單 → **向量健康**

顯示目前向量索引狀態，包含：

- 已索引段落總數
- 各文件的向量段落數量
- 孤立向量（無對應文件）偵測

---

## 8. Ollama 模型設定

本系統使用三個 Ollama 模型：

| 用途 | 預設模型 | 說明 |
|------|---------|------|
| LLM（問答 / 摘要） | `qwen3:8b` | 支援思考模式（think），回答品質佳 |
| 視覺模型（VL） | `qwen2.5vl:7b` | 辨識圖片、圖表、表格、嵌入文字 |
| 向量嵌入（Embedding） | `qwen3-embedding:8b` | 文字向量化，支援中文語意搜尋 |

### 下載模型

```bash
ollama pull qwen3:8b
ollama pull qwen2.5vl:7b
ollama pull qwen3-embedding:8b
```

### 切換模型

編輯 `backend/.env`：

```env
OLLAMA_LLM_MODEL=qwen3:8b
OLLAMA_VISION_MODEL=qwen2.5vl:7b
OLLAMA_EMBED_MODEL=qwen3-embedding:8b
```

修改後需重啟 backend 才會生效：

```bash
# Docker 模式
docker restart ai_document_v3-backend-1

# 原生模式
# 重新執行 uv run uvicorn ...
```

### 多頁分析頁數 vs 上下文建議

`OLLAMA_NUM_CTX` 決定模型一次能處理的最大 token 數，影響多頁 VL 分析的上限：

| `OLLAMA_NUM_CTX` | 建議 `MAX_PDF_ANALYSIS_PAGES` |
|-----------------|-------------------------------|
| 8192            | 3 頁                           |
| 16384           | 5 頁                           |
| 32768           | 10 頁                          |
| 65536           | 20 頁                          |

---

## 9. 環境變數參考

`backend/.env` 完整說明：

```env
# 資料庫
DATABASE_URL=sqlite:///./doc_management.db

# JWT 安全性（必填，建議 64 字元以上隨機字串）
SECRET_KEY=換成你自己的長隨機字串
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# 預設管理員（首次啟動時建立）
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=Admin@123
DEFAULT_ADMIN_EMAIL=admin@example.com

# Ollama 連線
OLLAMA_BASE_URL=http://host.docker.internal:11434   # Docker 內連宿主機
# OLLAMA_BASE_URL=http://127.0.0.1:11434            # 原生啟動時

OLLAMA_LLM_MODEL=qwen3:8b
OLLAMA_VISION_MODEL=qwen2.5vl:7b
OLLAMA_EMBED_MODEL=qwen3-embedding:8b
OLLAMA_KEEP_ALIVE=24h        # 模型在記憶體保留時間
OLLAMA_TIMEOUT=600           # 請求逾時秒數

# 生成參數
OLLAMA_NUM_PREDICT=-1        # -1 = 不限制輸出長度
OLLAMA_NUM_CTX=16384         # 上下文視窗大小
OLLAMA_STOP=<|endoftext|>,<|im_end|>,</s>

# 檔案儲存路徑
FILE_STORAGE_DIR=./storage
PDF_STORAGE_DIR=./storage/documents
PDF_TEMP_DIR=./storage/tmp
FAISS_INDEX_PATH=./storage/faiss_index.bin

# 向量搜尋參數
MIN_SIMILARITY_SCORE=0.3     # 最低相似度閾值（0–1）
DEFAULT_TOP_K=5              # 預設返回來源段落數
SEARCH_MULTIPLIER=10         # 實際搜尋數 = top_k × multiplier

# VL 多頁分析上限
MAX_PDF_ANALYSIS_PAGES=5
```

---

## 10. 常見問題

### Q：上傳文件後搜尋不到內容？

可能原因：
1. Ollama embedding 模型未啟動 → 執行 `ollama pull qwen3-embedding:8b` 並確認 Ollama 服務正在運行
2. 文件尚在向量化中 → 稍等片刻後重新整理
3. 圖片型 PDF 未選擇 VL 解析 → 至文件詳細頁觸發重新向量化（管理員）

### Q：VL 分析沒有描述圖片？

確認：
- 使用的是視覺模型（`OLLAMA_VISION_MODEL=qwen2.5vl:7b`）
- 模型已下載完成：`ollama list` 確認清單中有 `qwen2.5vl:7b`

### Q：多頁分析出現亂碼（`<|im_start|>` 重複）？

原因：`OLLAMA_NUM_CTX` 不足，模型上下文溢出。
解決：增大 `OLLAMA_NUM_CTX` 或減少 `MAX_PDF_ANALYSIS_PAGES`，參考[上方對照表](#多頁分析頁數-vs-上下文建議)。

### Q：區網內其他電腦如何連線使用？

確認宿主機 IP（例如 `192.168.1.188`），其他電腦直接瀏覽：

```
http://192.168.1.188:3000
```

frontend 預設在 port 3000，backend API 在 port 8000。

### Q：Docker 模式下 Ollama 無法連線？

確認 `backend/.env` 的 `OLLAMA_BASE_URL`：

- **macOS / Windows Docker Desktop**：使用 `http://host.docker.internal:11434`
- **Linux**：使用宿主機實際 IP，例如 `http://192.168.1.188:11434`

### Q：忘記管理員密碼？

直接修改 `backend/.env` 中的 `DEFAULT_ADMIN_PASSWORD`，**刪除資料庫檔案** `backend/doc_management.db` 後重啟，系統會重新建立預設帳號。

> 注意：刪除資料庫會清除所有文件、向量索引、對話紀錄。若只是要重設密碼，建議改用 SQLite 工具直接修改 users 資料表。

### Q：如何備份資料？

需備份的項目：

```
backend/doc_management.db          # 資料庫（文件 metadata、使用者、筆記等）
backend/storage/                   # PDF 原始檔與向量索引
backend/.env                       # 環境設定
```

---

*如有其他問題，請至 [GitHub Issues](https://github.com/hoyoboy0726123/AI_Document_V3/issues) 回報。*
