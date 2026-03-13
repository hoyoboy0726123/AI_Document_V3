# AI 文件管理系統 OCR 方案評估與建議報告

## 1. 問題背景

目前系統在上傳 PDF 文件時，依賴 `pdfminer` 套件進行文字擷取。此套件僅能處理包含數位文字層的 PDF，對於由掃描或圖片產生的純圖片 PDF，無法提取任何文字內容。這導致此類文件被系統標記為 `is_image_based`，但其內容無法被後續的向量化和 RAG (檢索增強生成) 流程處理，使得使用者無法透過問答方式檢索這些文件的內容。

## 2. 專案架構分析

- **文件上傳與處理 (`/api/v1/documents.py`)**:
  - `upload_pdf_for_extraction` 函式處理文件上傳。
  - 使用 `pdfminer` 提取文字後，透過 `len(text.strip()) < 100` 的判斷來識別純圖片 PDF。
  - 對於圖片型 PDF，當前流程中止，不進行內容處理。

- **文字擷取 (`/services/pdf_processing.py`)**:
  - `extract_text_and_segments` 函式是文字擷取的核心，完全依賴 `pdfminer`，這是目前的功能瓶頸。

- **向量化與 RAG (`/services/documents.py`, `/services/vector_store.py`)**:
  - `_rebuild_document_chunks` 函式負責將文字段落 (`segments`) 切割成塊 (`chunks`)，並呼叫 AI 服務生成向量，最終存入 Faiss 索引中。
  - 由於圖片型 PDF 沒有 `segments`，因此它們從未被向量化。

**結論**: 系統架構清晰，問題明確地集中在缺乏對圖片型 PDF 的光學字元辨識 (OCR) 能力。

## 3. OCR 方案評估

我們評估了兩種主流的開源 OCR 方案：專門的 OCR 工具 (Umi-OCR) 和大型多模態模型 (Qwen-VL)。

### 方案比較表

| 評估維度 | 方案 A: Umi-OCR | 方案 B: Qwen-VL | 推薦度 |
| :--- | :--- | :--- | :--- |
| **整合難度** | **低** (提供 HTTP API，易於整合) | **中等** (需在後端自行管理模型，程式碼較複雜) | ⭐️⭐️⭐️⭐️⭐️ |
| **準確度** | **高** (基於 PaddleOCR，中英文混合辨識準確率高) | **非常高** (除文字外，還能理解版面和結構) | ⭐️⭐️⭐️⭐️ |
| **效能/速度** | **快** (專門優化的 OCR 工具，適合即時處理) | **慢** (大模型推理速度較慢，可能成為瓶頸) | ⭐️⭐️⭐️⭐️⭐️ |
| **部署成本** | **低** (可在 CPU 上高效運行，無需 GPU) | **非常高** (需要至少 15GB+ VRAM 的高階 GPU) | ⭐️⭐️⭐️⭐️⭐️ |
| **部署複雜度**| **低** (可作為獨立 Docker 容器部署) | **高** (需管理大型模型檔案和複雜的 Python 環境) | ⭐️⭐️⭐️⭐️⭐️ |

### 方案 A: Umi-OCR

- **優點**:
  - **成本效益極高**: 無需 GPU，部署硬體成本低。
  - **整合簡單**: 可作為一個獨立的微服務，透過簡單的 HTTP POST 請求即可整合，與現有後端架構解耦。
  - **高效能**: 專為 OCR 任務設計，辨識速度快。
  - **高準確度**: PaddleOCR 引擎確保了優異的辨識效果。

- **缺點**:
  - 功能較為單一，專注於文字辨識，不像 Qwen-VL 能進行複雜的版面理解。

### 方案 B: Qwen-VL

- **優點**:
  - **功能強大**: 不僅能 OCR，還能理解文件結構、表格、票據，並按指令輸出 JSON 等結構化資料。
  - **輸出靈活**: 可透過 Prompt Engineering 控制輸出格式。

- **缺點**:
  - **成本極高**: 對 VRAM 要求非常高 (15GB-24GB+)，導致硬體成本和營運成本劇增。
  - **效能瓶頸**: 推理速度較慢，不適合需要快速回應的場景。
  - **過度設計 (Overkill)**: 對於本專案「提取文字以供向量化」的核心需求來說，其複雜功能是多餘的。

## 4. 推薦方案與技術設計

**我們強烈推薦採用方案 A: Umi-OCR。**

其成本效益、高效能和易於整合的特點，完美契合本專案的需求，能在最低成本和最短開發時間內解決核心問題。

### 技術方案設計

1.  **部署 OCR 服務**:
    - 在專案中引入 `docker-compose.yml`，新增一個 `umi-ocr` 服務，以無頭模式 (`HEADLESS=true`) 運行，並將其 API 埠 (預設 1224) 暴露給後端服務。

2.  **修改後端**:
    - **`requirements.txt`**: 新增 `requests`, `pdf2image`, `Pillow`。
    - **`core/config.py`**: 新增 `UMI_OCR_URL` 設定，指向 Umi-OCR 服務的 API 地址。
    - **`services/pdf_processing.py` (核心修改點)**:
        - 建立一個新函式 `_extract_text_with_ocr(pdf_bytes: bytes)`，用於處理 OCR 邏輯。
          - 內部使用 `pdf2image` 將 PDF 頁面轉為圖片。
          - 遍歷圖片，將其轉換為 Base64，並透過 `requests.post` 呼叫 Umi-OCR API。
          - 收集所有頁面的辨識結果，組合成與 `pdfminer` 相同的 `segments` 格式。
        - 修改現有的 `extract_text_and_segments` 函式，實現 **混合處理策略**：
          - **Step 1**: 依舊嘗試使用 `pdfminer` 進行快速文字擷取。
          - **Step 2**: 檢查擷取到的文字量。若文字量足夠，直接返回結果。
          - **Step 3**: 若文字量不足 (判斷為圖片型 PDF)，則自動呼叫 `_extract_text_with_ocr` 函式，使用 OCR 進行深度文字擷取。

    - **`api/v1/documents.py`**:
        - 簡化 `upload_pdf_for_extraction` 函式。由於 `extract_text_and_segments` 現在具備了處理所有類型 PDF 的能力，可以移除原本針對 `is_image_based` 的特殊處理分支，讓所有文件都能順利進入後續的 AI 摘要和向量化流程。

## 5. 實作步驟概要

1.  **環境準備**: 在 Docker 環境中安裝 `poppler-utils`。
2.  **部署 Umi-OCR**: 完成 `docker-compose.yml` 配置並啟動 Umi-OCR 服務。
3.  **修改依賴與設定**: 更新 `requirements.txt` 和 `config.py`。
4.  **開發 OCR 邏輯**: 在 `pdf_processing.py` 中實現 OCR API 呼叫與混合處理策略。
5.  **簡化 API 邏輯**: 移除 `documents.py` 中的冗餘分支。
6.  **完整測試**: 進行端對端測試，上傳純圖片 PDF，驗證文字是否能被成功提取，並能在 RAG 問答中被檢索到。

## 6. 預估工作量

- **後端開發 (含單元測試)**: 2-3 天
- **部署與整合測試**: 1 天
- **總計**: **約 3-4 個工作天**
