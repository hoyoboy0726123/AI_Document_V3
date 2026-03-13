from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import io
import logging

import numpy as np
from PIL import Image

from .pdf_image import get_pdf_page_count, pdf_page_to_image

logger = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR  # type: ignore
except Exception:  # pragma: no cover
    PaddleOCR = None


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


def _build_paddle_ocr() -> "PaddleOCR":
    if PaddleOCR is None:
        raise RuntimeError("PaddleOCR 未安裝，請先在 backend 環境安裝 paddleocr")

    # 第一版只做一般 OCR；表格結構保留留到下一階段接 PP-Structure
    return PaddleOCR(
        use_angle_cls=True,
        lang="ch",
        enable_mkldnn=False,
    )


def extract_image_pdf_blocks(pdf_path: str) -> List[Dict[str, Any]]:
    """圖片型 PDF OCR：逐頁轉圖後交由 PaddleOCR 抽文字。"""
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
