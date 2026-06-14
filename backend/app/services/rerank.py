"""撈寬再精選（rerank）：對檢索候選打分重排，把「真正含規格/判定/程序」的乾淨段落
排到前面、把修訂紀錄/續頁/目錄等垃圾踢掉，再餵生成。

兩種後端（RAG_RERANK_BACKEND）：
- cross_encoder：專門的 cross-encoder 模型（CPU），~1-3s，業界標準、品質佳，建議。
- llm：用既有生成模型（gemma）打分，零安裝但很慢（本機 ~100s）。

任何失敗（模型載入 / 呼叫 / 解析）都退回原順序，絕不讓檢索整個壞掉。
cross_encoder 載入失敗會自動降級到 llm。
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import List, Optional, Tuple

from ..core.config import settings
from . import ai

logger = logging.getLogger(__name__)

_SNIPPET_CHARS = 500

# ── cross-encoder 後端 ───────────────────────────────────────────────
_CE_MODEL = None
_CE_LOCK = threading.Lock()
_CE_FAILED = False  # 載入失敗就不再重試，直接走 llm


def _get_cross_encoder():
    """延遲載入 cross-encoder（單例，CPU）。失敗回 None 並標記降級。"""
    global _CE_MODEL, _CE_FAILED
    if _CE_MODEL is not None:
        return _CE_MODEL
    if _CE_FAILED:
        return None
    with _CE_LOCK:
        if _CE_MODEL is not None:
            return _CE_MODEL
        if _CE_FAILED:
            return None
        try:
            import os

            from sentence_transformers import CrossEncoder

            model_name = getattr(settings, "RAG_RERANK_MODEL", "BAAI/bge-reranker-base")
            logger.info("rerank: loading cross-encoder %s (cpu) ...", model_name)
            # 離線優先：已快取就免連網（秒載、無網路也可用，利於打包 .exe）；沒快取再允許下載。
            prev = os.environ.get("HF_HUB_OFFLINE")
            try:
                os.environ["HF_HUB_OFFLINE"] = "1"
                _CE_MODEL = CrossEncoder(model_name, device="cpu", max_length=512)
            except Exception:
                os.environ["HF_HUB_OFFLINE"] = "0"
                _CE_MODEL = CrossEncoder(model_name, device="cpu", max_length=512)
            finally:
                if prev is None:
                    os.environ.pop("HF_HUB_OFFLINE", None)
                else:
                    os.environ["HF_HUB_OFFLINE"] = prev
            logger.info("rerank: cross-encoder loaded")
            return _CE_MODEL
        except Exception as e:
            _CE_FAILED = True
            logger.warning("rerank: cross-encoder load failed, fallback to llm: %s", e)
            return None


def _score_cross_encoder(query: str, candidates) -> Optional[List[float]]:
    model = _get_cross_encoder()
    if model is None:
        return None
    try:
        pairs = [
            (query, (getattr(c, "text", "") or "")[:_SNIPPET_CHARS])
            for c, _ in candidates
        ]
        scores = model.predict(pairs)
        return [float(s) for s in scores]
    except Exception as e:
        logger.warning("rerank: cross-encoder predict failed: %s", e)
        return None


# ── llm 後端（gemma 打分）────────────────────────────────────────────
_RERANK_SYSTEM = (
    "You are a passage relevance rater for a document QA system. "
    "Output ONLY valid JSON, no prose, no markdown."
)

_RERANK_TEMPLATE = """\
針對使用者問題，為每個候選段落的「相關性」打 0-10 分。

評分標準：
- 8-10：段落直接包含問題主題的規格 / 判定標準 / 測試程序 / 數值等實質內容。
- 4-7：段落屬於該主題但只是片段、續頁或摘要。
- 0-3：與問題主題無關，或屬於修訂紀錄、目錄、版權頁、無意義表格殘片等。

使用者問題：
{question}

候選段落：
{passages}

只輸出 JSON，格式為 {{"1": 分數, "2": 分數, ...}}，鍵為段落編號、值為 0-10 整數。"""


def _parse_scores(raw: str) -> dict:
    if not raw:
        return {}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    candidate = m.group(0) if m else raw
    try:
        data = json.loads(candidate)
        out = {}
        for k, v in data.items():
            try:
                out[int(str(k).strip())] = float(v)
            except (ValueError, TypeError):
                continue
        return out
    except Exception:
        out = {}
        for km, vm in re.findall(r'"?(\d+)"?\s*:\s*(\d+(?:\.\d+)?)', candidate):
            out[int(km)] = float(vm)
        return out


def _score_llm(query: str, candidates) -> Optional[dict]:
    passages = []
    for i, (chunk, _) in enumerate(candidates, start=1):
        text = (getattr(chunk, "text", "") or "")[:_SNIPPET_CHARS].replace("\n", " ").strip()
        page = getattr(chunk, "page", None)
        passages.append(f"[{i}] (第{page}頁) {text}")
    prompt = _RERANK_TEMPLATE.format(question=query, passages="\n\n".join(passages))
    messages = [
        {"role": "system", "content": _RERANK_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = ai._chat_with_ollama(messages, response_format="json", think=False)
    except Exception as e:
        logger.warning("rerank llm call failed: %s", e)
        return None
    return _parse_scores(raw)


# ── 對外入口 ─────────────────────────────────────────────────────────
def rerank(query: str, candidates: List[Tuple[object, float]], top_n: int):
    """對 candidates=[(chunk, score)] 重排，回傳重排後的 [(chunk, score)]（最多 top_n）。

    失敗時回傳原順序的前 top_n。
    """
    if not candidates:
        return []
    if not getattr(settings, "RAG_RERANK", True) or len(candidates) <= 1:
        return candidates[:top_n]

    backend = getattr(settings, "RAG_RERANK_BACKEND", "cross_encoder")

    # 1) cross-encoder（優先）
    if backend == "cross_encoder":
        scores = _score_cross_encoder(query, candidates)
        if scores is not None:
            min_score = getattr(settings, "RAG_RERANK_CE_MIN_SCORE", 0.0)
            ranked = [
                (c, orig, scores[i], i)
                for i, (c, orig) in enumerate(candidates)
            ]
            kept = [r for r in ranked if r[2] >= min_score] or ranked
            kept.sort(key=lambda r: (-r[2], r[3]))
            logger.info(
                "rerank[cross_encoder]: %d -> %d kept (top_n=%d)",
                len(candidates), len(kept), top_n,
            )
            return [(c, orig) for c, orig, _s, _i in kept][:top_n]
        # cross-encoder 不可用 → 降級到 llm

    # 2) llm 後端
    scores_map = _score_llm(query, candidates)
    if not scores_map:
        logger.warning("rerank: no scores, keeping original order")
        return candidates[:top_n]

    min_score = getattr(settings, "RAG_RERANK_MIN_SCORE", 3)
    ranked = []
    for i, (chunk, orig_score) in enumerate(candidates, start=1):
        s = scores_map.get(i, float(min_score))
        ranked.append((chunk, orig_score, s, i))
    kept = [r for r in ranked if r[2] >= min_score] or ranked
    kept.sort(key=lambda r: (-r[2], r[3]))
    logger.info("rerank[llm]: %d -> %d kept (top_n=%d)", len(candidates), len(kept), top_n)
    return [(chunk, orig_score) for chunk, orig_score, _s, _i in kept][:top_n]
