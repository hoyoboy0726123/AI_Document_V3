# AI_Document_V3 開發計劃書

## 1. 專案目標
AI_Document_V3 是從 AI_Document_V2 複製出的獨立版本，目標是在 **不影響 V2** 的前提下，重構文件 OCR / 表格保留 / 向量化流程。

主要目標：
- 圖片型 PDF 可穩定做 OCR
- 表格盡量保留結構，不要被壓平成純文字
- OCR 後內容能順利進入 chunking 與向量化
- 建立「快速 OCR 主流程 + VLM fallback」架構

---

## 2. 現況盤點（已確認）

### 2.1 上傳入口
- 檔案：`backend/app/api/v1/documents.py`
- 入口：`POST /upload/`
- 現行做法：
  1. 先用 `extract_text_and_segments(pdf_bytes)` 嘗試抽文字
  2. 若抽到的文字長度 `< 100`，判定為 `is_image_based=True`
  3. 圖片型 PDF 先回前端，不會在這個階段完成 OCR 文字抽取

### 2.2 純文字 PDF 抽取
- 檔案：`backend/app/services/pdf_processing.py`
- 核心函式：
  - `extract_text_and_segments()`
  - `split_segments_into_chunks()`
- 現行做法：
  - 使用 `pdfminer` 取文字與段落
  - 依 `max_chars + overlap_chars` 做 chunking

### 2.3 chunk 與向量化入口
- 檔案：`backend/app/services/documents.py`
- 核心函式：
  - `_rebuild_document_chunks()`
  - `_re_embed_existing_chunks()`
- 現行做法：
  1. 從 segments 生成 chunk payloads
  2. 產生 `DocumentChunk`
  3. 呼叫 `ai.embed_texts()`
  4. 寫入 DB 與 FAISS

### 2.4 Embedding 與模型設定
- 檔案：
  - `backend/app/core/config.py`
  - `backend/.env_example`
- 現行預設：
  - `OLLAMA_LLM_MODEL=llama3.2`
  - `OLLAMA_VISION_MODEL=llava`
  - `OLLAMA_EMBED_MODEL=all-minilm`

### 2.5 Vision / PDF 圖像分析能力
- 檔案：`backend/app/services/ai.py`
- 已有能力：
  - `analyze_pdf_page_images()`
  - `analyze_pdf_page_images_stream()`
  - `analyze_pdf_page_images_singleturn()`
- 現況：
  - 已能將 PDF 頁面轉圖後交給 vision model 分析
  - 但這套流程目前偏「問答/分析」，不是正式 OCR ingestion pipeline

### 2.6 PDF 圖像工具
- 檔案：`backend/app/services/pdf_image.py`
- 功能：
  - PDF 轉單頁/多頁圖片
  - 取得總頁數

---

## 3. 問題定義
目前 V2/V3 的核心問題：

1. **圖片型 PDF 沒有完整 OCR ingestion**
   - 目前只會檢測 `is_image_based`
   - 沒有把 OCR 結果正式餵回 chunk / embedding pipeline

2. **表格沒有結構保留機制**
   - 現行 `split_segments_into_chunks()` 假設輸入都是線性段落文字
   - 表格會被打散或丟失欄列結構

3. **Vision 模型目前偏互動分析，不是專用 OCR pipeline**
   - 適合問答與理解
   - 不一定適合大量批次 OCR

---

## 4. V3 新架構提案

### 4.1 雙層 OCR 架構

#### A. 主流程（快速）
使用專用 OCR / 文件解析工具：
- PaddleOCR
- PP-Structure / Table Structure Recognition

用途：
- 一般文字 OCR
- 表格結構辨識
- 文件版面分析

#### B. 補強流程（準確度 fallback）
使用 VLM：
- Qwen2.5-VL / 更強的 Qwen 系列
- 或保留現有 `OLLAMA_VISION_MODEL`

用途：
- OCR 信心不足的頁面
- 複雜圖文混排
- 專用 OCR 難處理的頁面

---

## 5. 資料流重構方向

### 現行資料流
PDF → pdfminer 取文字 → segments → chunks → embeddings → FAISS

### V3 目標資料流

#### 文字型 PDF
PDF → pdfminer 取文字 → segments → chunks → embeddings → FAISS

#### 圖片型 PDF
PDF → 轉圖片 → OCR/表格解析 → 標準化 segments/table_blocks → chunks → embeddings → FAISS

#### 複雜頁面 fallback
PDF → 圖片 → 專用 OCR → 若失敗/低信心 → VLM 補強 → 標準化 → chunks → embeddings

---

## 6. 表格保留設計

### 6.1 新增區塊類型
預計把 chunk 前的中間資料標準化為：
- `paragraph`
- `table`
- `caption`
- `figure_note`（必要時）

### 6.2 table block 建議格式
每個表格區塊保留：
- 頁碼
- 表格原始內容
- HTML / Markdown / JSON 結構
- 純文字 fallback

### 6.3 chunking 策略
- 段落：沿用現有 chunking
- 表格：
  - 小表格可整表成一個 chunk
  - 大表格可依表頭 + 列切分
- metadata 保留：
  - `block_type`
  - `table_index`
  - `page`

---

## 7. 分階段開發順序

### Phase 1：專案識別整理
- [ ] 專案名稱改為 AI_Document_V3
- [ ] 安裝/說明文件標註 V3 為 OCR 重構版本

### Phase 2：OCR 管線插槽化
- [ ] 新增 OCR service 抽象層
- [ ] 保留現有 pdfminer 作為文字型 PDF 路徑
- [ ] 新增圖片型 PDF ingestion 路徑

### Phase 3：PaddleOCR/表格結構整合
- [ ] 引入 PaddleOCR / PP-Structure
- [ ] OCR 結果標準化成 segments / table blocks
- [ ] 建立表格結構保存格式

### Phase 4：chunking 重構
- [ ] chunker 支援 paragraph + table
- [ ] chunk metadata 擴充

### Phase 5：embedding / vector store 相容
- [ ] 確保新 block 結構可以安全進 FAISS
- [ ] 重新檢查搜尋與 RAG 回答輸出

### Phase 6：前端支援
- [ ] 顯示 OCR 狀態 / OCR 方法
- [ ] 顯示是否含表格結構
- [ ] 預覽頁加入 OCR / table block debug 視圖（必要時）

---

## 8. 第一輪開發建議（最小可行版本）
第一輪先不要一次做到太滿，先達成：

1. 圖片型 PDF 能正式 OCR
2. OCR 結果能進 chunk / embedding
3. 至少保留簡單表格的 Markdown/HTML 結構

也就是先完成：
- `圖片 PDF → OCR → 向量化`

再進一步做：
- 高級表格保留
- fallback 智能切換
- 前端可視化

---

## 9. 我下一步準備做的事
1. 建立 OCR service 抽象層
2. 定義 OCR block 標準資料結構
3. 找出 `upload -> create document -> rebuild chunks` 的最小切入點
4. 先讓圖片型 PDF 不再只是 `pending`，而是真的能被 OCR 並進向量化

---

## 10. 目前判斷
V3 最關鍵的切入點不是前端，而是：
- `backend/app/api/v1/documents.py`
- `backend/app/services/documents.py`
- `backend/app/services/pdf_processing.py`
- 新增 `backend/app/services/ocr_pipeline.py`（建議）

接下來建議從 **ocr pipeline 抽象層** 開始做。
