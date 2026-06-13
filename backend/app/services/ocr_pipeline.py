from __future__ import annotations

import os

# Paddle 3.3.x 的 PIR + OneDNN 新執行器在 Windows CPU 有 regression
# (ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<...>])。
# 主要修法是 pyproject.toml 鎖到 paddlepaddle 3.2.2 + paddleocr 3.4.1；
# 下面這幾個 FLAGS 是保險絲，若未來不小心升上去也能多一道防線
# (注意：實測 PIR 新執行器會忽略這些 legacy toggle，所以不能單靠它們)。
# 上游 issue：https://github.com/PaddlePaddle/Paddle/issues/77340
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_use_pir_in_executor", "0")

from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
import io
import logging
import re

import numpy as np
from PIL import Image

from .pdf_image import get_pdf_page_count, pdf_page_to_image

logger = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR  # type: ignore
except Exception:  # pragma: no cover
    PaddleOCR = None

try:
    from paddleocr import PPStructureV3  # type: ignore
except Exception:  # pragma: no cover
    PPStructureV3 = None


@dataclass
class OCRBlock:
    block_type: str  # paragraph | table | caption | figure_note
    text: str
    page: Optional[int] = None
    paragraph_index: Optional[int] = None
    table_index: Optional[int] = None
    html: Optional[str] = None
    markdown: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_ocr_blocks(blocks: List[OCRBlock]) -> List[Dict[str, Any]]:
    """將 OCR block 標準化成可供 chunking 使用的 dict 結構。"""
    normalized: List[Dict[str, Any]] = []
    for idx, block in enumerate(blocks):
        text = (block.text or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "block_type": block.block_type,
                "text": text,
                "page": block.page,
                "paragraph_index": block.paragraph_index if block.paragraph_index is not None else idx + 1,
                "table_index": block.table_index,
                "html": block.html,
                "markdown": block.markdown,
                "metadata": block.metadata or {},
            }
        )
    return normalized


class _HTMLTableParser(HTMLParser):
    """Minimal stdlib HTML-table → 2D-grid parser. No new deps."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._cur_row: Optional[List[str]] = None
        self._cur_cell: Optional[List[str]] = None
        self._in_table = False
        self._span_pending: int = 1  # colspan for current cell

    def handle_starttag(self, tag: str, attrs: List) -> None:
        tag = tag.lower()
        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._cur_row = []
        elif tag in ("td", "th") and self._cur_row is not None:
            self._cur_cell = []
            self._span_pending = 1
            for k, v in attrs:
                if k.lower() == "colspan":
                    try:
                        self._span_pending = max(1, int(v))
                    except Exception:
                        pass
        elif tag == "br" and self._cur_cell is not None:
            self._cur_cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "table":
            self._in_table = False
        elif tag == "tr" and self._cur_row is not None:
            if self._cur_row:
                self.rows.append(self._cur_row)
            self._cur_row = None
        elif tag in ("td", "th") and self._cur_cell is not None and self._cur_row is not None:
            cell_text = re.sub(r"\s+", " ", "".join(self._cur_cell)).strip()
            self._cur_row.append(cell_text)
            # Fill colspan with empty cells
            for _ in range(self._span_pending - 1):
                self._cur_row.append("")
            self._cur_cell = None
            self._span_pending = 1

    def handle_data(self, data: str) -> None:
        if self._cur_cell is not None:
            self._cur_cell.append(data)


def _html_table_to_markdown(html: str) -> str:
    """Convert an HTML <table> string into Markdown pipe-table syntax.

    Uses stdlib html.parser; rejects rows that diverge in column count by padding
    to the widest row. Returns "" if no rows extracted.
    """
    if not html or "<" not in html:
        return ""
    parser = _HTMLTableParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        logger.debug("HTML table parse failed: %s", exc)
        return ""

    rows = parser.rows
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]

    md_lines: List[str] = []
    header = norm[0]
    md_lines.append("| " + " | ".join(c or " " for c in header) + " |")
    md_lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in norm[1:]:
        md_lines.append("| " + " | ".join(c or " " for c in row) + " |")
    return "\n".join(md_lines)


def _build_paddle_ocr() -> "PaddleOCR":
    if PaddleOCR is None:
        raise RuntimeError("PaddleOCR 未安裝，請先在 backend 環境安裝 paddleocr")

    # PaddleOCR 3.4.0 + paddlepaddle 3.3.1 在 Windows CPU 上：
    # 1) 預設啟用的 doc_orientation / doc_unwarping / textline_orientation 預處理會觸發 segfault
    # 2) 預設的 server 模型 (PP-OCRv5_server_det/rec) 在 rec 階段 segfault；mobile 模型穩定
    # 因此這裡明確關閉預處理並改用 mobile 模型。
    return PaddleOCR(
        lang="ch",
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
    )


def _build_pp_structure() -> "PPStructureV3":
    if PPStructureV3 is None:
        raise RuntimeError("PPStructureV3 未安裝，請先 pip install 'paddlex[ocr]'")

    # Windows CPU 已知問題：
    # - MKLDNN/onednn 在 layout/table 模型上會丟 ConvertPirAttribute2RuntimeAttribute 錯
    #   → 由 module 載入時的 FLAGS_use_mkldnn=0 統一關閉
    # - server 級 OCR 模型 (PP-OCRv5_server_det/rec) 會 segfault → 改用 mobile
    return PPStructureV3(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
    )


_TEXT_BLOCK_LABELS = {
    "text",
    "paragraph",
    "paragraph_title",
    "doc_title",
    "title",
    "abstract",
    "content",
    "header",
    "footer",
    "reference",
    "list",
}
_TABLE_BLOCK_LABELS = {"table"}
_SKIP_BLOCK_LABELS = {"figure", "image", "chart", "seal", "formula_number"}


def _block_field(block: Any, *keys: str) -> Any:
    """PPStructureV3 block 可能是 dict 或 object — 兩種都支援。"""
    for k in keys:
        if isinstance(block, dict) and k in block:
            return block[k]
        if hasattr(block, k):
            return getattr(block, k)
    return None


def _extract_layout_blocks(page_result: Any) -> List[Any]:
    """從一個 PPStructureV3 page result 取出 layout blocks list。"""
    candidates = (
        "parsing_res_list",
        "layout_parsing_res",
        "parsing_res",
        "layout_det_res",
        "blocks",
    )
    for key in candidates:
        if isinstance(page_result, dict) and key in page_result:
            value = page_result[key]
            if isinstance(value, list) and value:
                return value
        if hasattr(page_result, key):
            value = getattr(page_result, key)
            if isinstance(value, list) and value:
                return value
    return []


_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)


def _replace_html_tables_with_markdown(text: str) -> str:
    """Find every <table>...</table> in `text` and replace it with markdown pipe-table.

    Falls back to the original HTML if our parser can't extract rows (e.g. table
    with rowspan we don't support). Non-table content is left untouched.
    """
    if not text or "<table" not in text.lower():
        return text

    def _sub(match: "re.Match[str]") -> str:
        html = match.group(0)
        md = _html_table_to_markdown(html)
        return f"\n\n{md}\n\n" if md else html

    return _TABLE_RE.sub(_sub, text)


def extract_image_pdf_blocks_with_structure(pdf_path: str) -> List[Dict[str, Any]]:
    """以 PP-StructureV3 做版面分析，輸出含 markdown 表格的逐頁文字。

    使用 PaddleX 原生 `_to_markdown(pretty=False)` 拿到整頁 markdown
    (標題/段落/列表都已格式化、表格保留為乾淨的 `<table>...</table>`)，
    再把每個 `<table>` 區塊用 `_html_table_to_markdown()` 轉成 markdown 管線表格。
    """
    pipeline = _build_pp_structure()
    page_count = get_pdf_page_count(pdf_path)
    if page_count <= 0:
        return []

    blocks: List[OCRBlock] = []

    for page_num in range(1, page_count + 1):
        img_bytes = pdf_page_to_image(pdf_path, page_num, dpi=200, max_dimension=2200)
        if not img_bytes:
            logger.warning("PPStructure 跳過頁面 %s：轉圖失敗", page_num)
            continue

        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_array = np.array(img)
        except Exception as exc:
            logger.warning("PPStructure 跳過頁面 %s：圖片解碼失敗 (%s)", page_num, exc)
            continue

        try:
            result = pipeline.predict(img_array)
        except Exception as exc:
            logger.warning("PPStructure 第 %s 頁推論失敗 (%s)，將改用 basic OCR", page_num, exc)
            raise

        page_paragraphs = 0
        for page_result in result or []:
            try:
                md_dict = page_result._to_markdown(pretty=False)
            except Exception as exc:
                logger.warning("PPStructure 第 %s 頁 _to_markdown 失敗 (%s)，跳過", page_num, exc)
                continue

            raw_markdown = (md_dict or {}).get("markdown_texts") or ""
            if not raw_markdown.strip():
                continue

            converted = _replace_html_tables_with_markdown(raw_markdown)

            # 以連續空行切段，每段一個 paragraph block —
            # split_segments_into_chunks 再依 max_chars 重新合併成向量塊。
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", converted) if p.strip()]
            for para in paragraphs:
                page_paragraphs += 1
                has_table = "|" in para and "---" in para
                blocks.append(
                    OCRBlock(
                        block_type="table" if has_table else "paragraph",
                        text=para,
                        page=page_num,
                        paragraph_index=page_paragraphs,
                        markdown=para if has_table else None,
                        metadata={"ocr_engine": "ppstructurev3"},
                    )
                )

        logger.info("PPStructure 完成第 %s 頁，抽出 %s 段 markdown", page_num, page_paragraphs)

    return normalize_ocr_blocks(blocks)


def extract_image_pdf_blocks(pdf_path: str) -> List[Dict[str, Any]]:
    """圖片型 PDF OCR：優先用 PP-StructureV3（表格→markdown），失敗則退回 PaddleOCR 純文字。"""
    if PPStructureV3 is not None:
        try:
            return extract_image_pdf_blocks_with_structure(pdf_path)
        except Exception as exc:
            logger.warning("PPStructureV3 整體流程失敗，改用 basic PaddleOCR：%s", exc)

    ocr = _build_paddle_ocr()
    page_count = get_pdf_page_count(pdf_path)
    if page_count <= 0:
        return []

    blocks: List[OCRBlock] = []

    for page_num in range(1, page_count + 1):
        img_bytes = pdf_page_to_image(pdf_path, page_num, dpi=200, max_dimension=2200)
        if not img_bytes:
            logger.warning("PaddleOCR 跳過頁面 %s：轉圖失敗", page_num)
            continue

        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_array = np.array(img)
        except Exception as exc:
            logger.warning("PaddleOCR 跳過頁面 %s：圖片解碼失敗 (%s)", page_num, exc)
            continue

        result = ocr.predict(img_array)
        page_lines: List[str] = []
        line_idx = 0

        for page_result in result or []:
            rec_texts = page_result.get("rec_texts", []) or []
            rec_scores = page_result.get("rec_scores", []) or []

            for idx, text_value in enumerate(rec_texts):
                text = str(text_value or "").strip()
                score = None
                if idx < len(rec_scores) and rec_scores[idx] is not None:
                    score = float(rec_scores[idx])
                if not text:
                    continue
                page_lines.append(text)
                line_idx += 1
                blocks.append(
                    OCRBlock(
                        block_type="paragraph",
                        text=text,
                        page=page_num,
                        paragraph_index=line_idx,
                        metadata={"ocr_engine": "paddleocr", "confidence": score},
                    )
                )

        logger.info("PaddleOCR 完成第 %s 頁，抽取 %s 行", page_num, len(page_lines))

    return normalize_ocr_blocks(blocks)
