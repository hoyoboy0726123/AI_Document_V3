import logging
import re
from collections import Counter
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

BLOCK_TYPE_PARAGRAPH = "paragraph"
BLOCK_TYPE_TABLE = "table"

from pdfminer.high_level import extract_pages, extract_text
from pdfminer.layout import LTTextContainer
from pdfminer.pdfdocument import PDFPasswordIncorrect

from .. import schemas

logger = logging.getLogger(__name__)


def extract_text_and_segments(pdf_bytes: bytes) -> Tuple[str, List[schemas.DocumentSegment]]:
    try:
        segments: List[schemas.DocumentSegment] = []
        sections: List[str] = []

        for page_number, page_layout in enumerate(extract_pages(BytesIO(pdf_bytes)), start=1):
            page_text_parts: List[str] = []
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    page_text_parts.append(element.get_text())

            page_text = "".join(page_text_parts).strip()
            if not page_text:
                continue

            sections.append(page_text)
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", page_text) if part.strip()]

            for idx, paragraph in enumerate(paragraphs, start=1):
                normalized = re.sub(r"\s+", " ", paragraph)
                if len(normalized) > 1000:
                    normalized = f"{normalized[:1000]}..."
                segments.append(schemas.DocumentSegment(page=page_number, paragraph_index=idx, text=normalized))

        combined_text = "\n\n".join(sections).strip()
        if combined_text:
            return combined_text, segments
    except PDFPasswordIncorrect:
        raise
    except Exception as exc:  # pragma: no cover - fallback to plain extraction
        logger.debug("Structured PDF extraction failed, fallback to plain text: %s", exc)

    try:
        plain_text = (extract_text(BytesIO(pdf_bytes)) or "").strip()
        return plain_text, []
    except PDFPasswordIncorrect:
        raise
    except Exception as exc:  # pragma: no cover
        logger.debug("Plain text extraction failed: %s", exc)
        return "", []


def suggest_keywords(text: str, limit: int = 8) -> List[str]:
    if not text:
        return []
    words = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", text.lower())
    stopwords = {"the", "and", "with", "this", "that", "from", "have", "will", "shall"}
    filtered = [w for w in words if w not in stopwords]
    counter = Counter(filtered)
    return [word for word, _ in counter.most_common(limit)]


def split_segments_into_chunks(
    segments: List[schemas.DocumentSegment],
    *,
    max_chars: int = 1800,
    overlap_chars: int = 250,
) -> List[Dict[str, Any]]:
    """
    將段落合併成向量塊，支援 overlap 重疊設計

    Args:
        segments: 文檔段落列表
        max_chars: 向量塊最大字符數（預設 1800）
        overlap_chars: 向量塊之間的重疊字符數（預設 250）

    Returns:
        向量塊列表，每個塊包含 chunk_index, page, paragraph_index, text
    """
    chunks: List[Dict[str, Any]] = []
    current_text: List[str] = []
    current_page: Optional[int] = None
    current_paragraph: Optional[int] = None
    chunk_index = 0

    for segment in segments:
        # 支援字典或物件兩種格式
        if isinstance(segment, dict):
            segment_text = segment.get("text", "").strip()
            seg_page = segment.get("page")
            seg_para = segment.get("paragraph_index")
        else:
            segment_text = segment.text.strip()
            seg_page = segment.page
            seg_para = segment.paragraph_index

        if not segment_text:
            continue

        prospective = "\n".join(current_text + [segment_text]) if current_text else segment_text
        if current_text and len(prospective) > max_chars:
            # 完成當前向量塊
            full_text = "\n".join(current_text)
            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "page": current_page,
                    "paragraph_index": current_paragraph,
                    "block_type": BLOCK_TYPE_PARAGRAPH,
                    "text": full_text,
                }
            )
            chunk_index += 1

            # 提取重疊部分作為下一個向量塊的開頭
            if len(full_text) > overlap_chars:
                overlap_text = full_text[-overlap_chars:]
                current_text = [overlap_text, segment_text]
            else:
                # 如果當前塊太短，無法提供足夠的重疊，就從新段落開始
                current_text = [segment_text]

            current_page = seg_page
            current_paragraph = seg_para
        else:
            if not current_text:
                current_page = seg_page
                current_paragraph = seg_para
            current_text.append(segment_text)

    if current_text:
        chunks.append(
            {
                "chunk_index": chunk_index,
                "page": current_page,
                "paragraph_index": current_paragraph,
                "block_type": BLOCK_TYPE_PARAGRAPH,
                "text": "\n".join(current_text),
            }
        )

    return chunks
