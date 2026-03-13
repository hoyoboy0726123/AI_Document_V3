import io
import logging
from typing import List, Optional
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def pdf_page_to_image(
    pdf_path: str,
    page_number: int,
    dpi: int = 150,
    max_dimension: int = 2048
) -> Optional[bytes]:
    """
    將 PDF 指定頁面轉換為 JPEG 圖片

    Args:
        pdf_path: PDF 文件路徑
        page_number: 頁碼（從 1 開始）
        dpi: 解析度（150 DPI 通常足夠，平衡質量和成本）
        max_dimension: 最大寬度或高度（像素），超過會縮小

    Returns:
        JPEG 圖片的 bytes，如果失敗返回 None
    """
    try:
        # 打開 PDF
        pdf_document = fitz.open(pdf_path)

        # 檢查頁碼有效性
        if page_number < 1 or page_number > len(pdf_document):
            logger.error(f"頁碼 {page_number} 超出範圍，PDF 共 {len(pdf_document)} 頁")
            return None

        # 獲取頁面（PyMuPDF 頁碼從 0 開始）
        page = pdf_document[page_number - 1]

        # 計算縮放比例（DPI 轉換）
        zoom = dpi / 72  # PDF 預設 72 DPI
        mat = fitz.Matrix(zoom, zoom)

        # 渲染為圖片
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # 轉換為 PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # 如果圖片太大，進行縮放
        if max(img.width, img.height) > max_dimension:
            ratio = max_dimension / max(img.width, img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            logger.info(f"圖片從 {pix.width}x{pix.height} 縮放到 {new_size[0]}x{new_size[1]}")

        # 轉換為 JPEG bytes
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="JPEG", quality=85, optimize=True)
        img_bytes = img_buffer.getvalue()

        pdf_document.close()

        logger.info(f"成功將 PDF 第 {page_number} 頁轉換為圖片，大小 {len(img_bytes)} bytes")
        return img_bytes

    except Exception as e:
        logger.error(f"PDF 轉圖片失敗：{e}", exc_info=True)
        return None


def pdf_pages_to_images(
    pdf_path: str,
    page_numbers: List[int],
    dpi: int = 150,
    max_dimension: int = 2048
) -> List[bytes]:
    """
    將 PDF 多個頁面轉換為圖片列表

    Args:
        pdf_path: PDF 文件路徑
        page_numbers: 頁碼列表（從 1 開始）
        dpi: 解析度
        max_dimension: 最大寬度或高度

    Returns:
        圖片 bytes 列表
    """
    images = []
    for page_num in page_numbers:
        img_bytes = pdf_page_to_image(pdf_path, page_num, dpi, max_dimension)
        if img_bytes:
            images.append(img_bytes)
        else:
            logger.warning(f"跳過頁面 {page_num}，轉換失敗")

    return images


def get_pdf_page_count(pdf_path: str) -> int:
    """
    獲取 PDF 總頁數

    Args:
        pdf_path: PDF 文件路徑

    Returns:
        總頁數，失敗返回 0
    """
    try:
        pdf_document = fitz.open(pdf_path)
        page_count = len(pdf_document)
        pdf_document.close()
        return page_count
    except Exception as e:
        logger.error(f"無法讀取 PDF 頁數：{e}")
        return 0
