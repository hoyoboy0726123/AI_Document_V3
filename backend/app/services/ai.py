import base64
import io
import json
import logging
from typing import Any, Dict, List, Optional

from PIL import Image

from ..core.config import settings
from .ollama_client import get_client

logger = logging.getLogger(__name__)


DOCUMENT_SUGGESTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "classification": {"type": "string"},
        "classification_is_new": {"type": "boolean"},
        "classification_reason": {"type": "string"},
        "project": {"type": "string"},
        "project_is_new": {"type": "boolean"},
        "project_reason": {"type": "string"},
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
        "metadata": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": [
        "summary",
        "classification",
        "classification_is_new",
        "keywords",
        "metadata",
    ],
}

FOLLOWUP_INTENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_followup": {"type": "boolean"},
        "needs_new_search": {"type": "boolean"},
        "optimized_query": {"type": "string"},
        "search_keywords": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": [
        "is_followup",
        "needs_new_search",
        "optimized_query",
        "search_keywords",
    ],
}

SUGGESTED_QUESTION_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 1,
    "maxItems": 5,
}


def _safe_json_loads(payload: str) -> Dict[str, Any]:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("LLM 回傳的 JSON 解析失敗：%s", payload)
        return {}


def _chat_with_ollama(
    messages: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    response_format: Optional[Any] = None,
    think: bool = False,
) -> str:
    import time
    client = get_client()
    t0 = time.time()
    result = client.chat(
        messages,
        model=model or settings.OLLAMA_LLM_MODEL,
        format=response_format,
        think=think,
    )
    elapsed = time.time() - t0
    logger.info("_chat_with_ollama elapsed=%.1fs think=%s output_len=%d preview=%s",
                elapsed, think, len(result), repr(result[:120]))
    return result


def _prepare_history(conversation_history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    # Local light-weight sanitizer to avoid leaking control tokens into prompts
    import re as _re

    def _scrub(text: str) -> str:
        if not text:
            return text
        cleaned = _re.sub(r"[\u200B\u200C\u200D\u2060\ufeff]", "", text)
        for t in (r"<\|im_start\|>", r"<\|im_end\|>", r"<\|assistant\|>", r"<\|user\|>", r"<s>", r"</s>", r"<<SYS>>", r"</SYS>"):
            cleaned = _re.sub(t, "", cleaned, flags=_re.IGNORECASE)
        cleaned = _re.sub(r"^(\s*)(assistant|user|system)\s*:\s*", r"\1", cleaned, flags=_re.IGNORECASE | _re.MULTILINE)
        return cleaned.strip()

    history: List[Dict[str, str]] = []
    if not conversation_history:
        return history

    for turn in conversation_history[-5:]:
        question = _scrub(turn.get("question") or "")
        answer = _scrub(turn.get("answer") or "")
        if question:
            history.append({"role": "user", "content": question})
        if answer:
            history.append({"role": "assistant", "content": answer})
    return history


def generate_document_suggestion(
    *,
    text: str,
    classifications: List[str],
    projects: List[str],
    segments: Optional[List[Dict[str, Any]]] = None,
    max_text_chars: int = 8000,
) -> Dict[str, Any]:
    client = get_client()
    truncated_text = (text or "").strip()[:max_text_chars]

    segments_summary = []
    if segments:
        for segment in segments[:20]:
            snippet = str(segment.get("text", "")).strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = f"{snippet[:200]}..."
            page = segment.get("page")
            paragraph = segment.get("paragraph_index")
            segments_summary.append(f"- Page {page} / Paragraph {paragraph}: {snippet}")

    prompt = f"""
You are an assistant that extracts document metadata, summary, keywords, and suggested classification/project values.
IMPORTANT: The summary MUST be in Traditional Chinese (Taiwan). Keywords should be in Traditional Chinese or English as appropriate.

Document snippet:
```
{truncated_text}
```

Available classifications:
{chr(10).join(f"- {item}" for item in classifications) if classifications else "- (none listed)"}

Available projects:
{chr(10).join(f"- {item}" for item in projects) if projects else "- (none listed)"}

Important segments:
{chr(10).join(segments_summary) if segments_summary else "-"}

Return a JSON object strictly following the provided schema.
"""

    raw_response = client.chat(
        [{"role": "user", "content": prompt}],
        model=settings.OLLAMA_LLM_MODEL,
        format=DOCUMENT_SUGGESTION_SCHEMA,
    )
    payload = _safe_json_loads(raw_response)

    return {
        "summary": payload.get("summary", ""),
        "classification": payload.get("classification"),
        "classification_is_new": bool(payload.get("classification_is_new")),
        "classification_reason": payload.get("classification_reason"),
        "project": payload.get("project"),
        "project_is_new": bool(payload.get("project_is_new")),
        "project_reason": payload.get("project_reason"),
        "keywords": payload.get("keywords") or [],
        "metadata": payload.get("metadata") or {},
    }


def generate_rag_answer(
    question: str,
    context_blocks: List[Dict[str, str]],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    if not question:
        raise ValueError('問題不可為空白')

    if not context_blocks:
        return '查無足夠的相關內容，請提供更多文件或調整問題。'

    PAGE_GAP_THRESHOLD = 5  # 頁碼差超過此值視為不同章節

    def _page_label(block: Dict, idx: int) -> str:
        page = block.get("page") or "?"
        gap = block.get("page_gap")
        if idx == 0 or gap is None:
            return f"第 {page} 頁"
        if gap <= PAGE_GAP_THRESHOLD:
            return f"第 {page} 頁（與主要來源相鄰，頁距 {gap}）"
        return f"第 {page} 頁 ⚠️ 頁距 {gap}，可能為不同章節"

    context_text = "\n\n".join(
        f"[來源{idx + 1}] {block.get('title') or '未命名段落'} ({_page_label(block, idx)})\n{(block.get('text') or '').strip()}"
        for idx, block in enumerate(context_blocks)
    )

    history_text = ""
    if conversation_history:
        recent = conversation_history[-2:]
        history_text = "\n".join(
            f"Q: {turn.get('question', '')}\nA: {turn.get('answer', '')}"
            for turn in recent
        )

    prompt = f"""
你是一位文件問答助理，只能根據「可用段落」作答。
原則：
- 僅引用與使用者問題直接相關的段落內容，其餘無關資訊請忽略。
- 盡可能完整重現參考資料中的細節（如背景、限制、程序、數值、條件），並保持語意清楚。
- 每個[來源]的資訊相互獨立，嚴格禁止跨來源拼湊細節（例如：不可將[來源2]的數值或條件套用到[來源1]的測試項目上）。
- 若多個來源涉及相似但不同的測試項目或主題，必須分開描述並明確標示各自來源，不可合併成同一段落。
- 標記「⚠️ 頁距 N，可能為不同章節」的來源極可能屬於不同測試項目：若其內容與問題主題不完全吻合，優先捨棄該來源；若仍引用，必須獨立描述並加以說明其來自不同章節，不可將其數值或條件與其他來源混用。
- 在回答文字中以 [來源1][來源3] 標示引用來源，可於同一句結尾列出多個來源。
- 若所有段落皆無法回答，請明確回覆「查無相關資料」，並建議提供更多上下文。
{f'- 參考對話歷史理解追問脈絡，但答案必須來自可用段落。' if history_text else ''}

{f'對話歷史（最近 2 輪）：{chr(10)}{history_text}{chr(10)}' if history_text else ''}
使用者問題：
{question}

可用段落：
{context_text}

請以下列格式輸出：
回答：
<可多段或條列，需保持細節並標註來源>
參考來源：
- [來源X] <此來源提供的重點>
""".strip()

    return _chat_with_ollama([
        {"role": "system", "content": "請務必使用「繁體中文（台灣）」回答，嚴格禁止簡體中文。避免輸出任何控制標記或思考過程。"},
        {"role": "user", "content": prompt},
    ], think=True)

_EMBED_MAX_CHARS = 7000  # qwen3-embedding:8b supports 8192 tokens (~7000 English chars)
_EMBED_BATCH_SIZE = 10   # process N chunks per request to avoid timeout

def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    client = get_client()
    truncated = [t[:_EMBED_MAX_CHARS] for t in texts]

    all_embeddings: List[List[float]] = []
    for i in range(0, len(truncated), _EMBED_BATCH_SIZE):
        batch = truncated[i:i + _EMBED_BATCH_SIZE]
        batch_embeddings = client.embed(
            batch,
            model=settings.OLLAMA_EMBED_MODEL,
        )
        all_embeddings.extend(batch_embeddings)

    if len(all_embeddings) != len(texts):
        raise RuntimeError("Ollama 回傳的 embedding 數量與輸入不符")
    return all_embeddings


def analyze_followup_intent(
    current_question: str,
    conversation_history: List[Dict[str, str]],
) -> Dict[str, object]:
    if not current_question:
        return {
            "is_followup": False,
            "needs_new_search": True,
            "optimized_query": "",
            "search_keywords": "",
            "reasoning": "",
        }

    history_text = "\n".join(
        f"Q: {turn.get('question')}\nA: {turn.get('answer')}\n"
        for turn in conversation_history[-3:]
    )

    prompt = f"""
You are an assistant that decides whether the latest question is a follow-up and produces ONE optimized search query.

Conversation history (most recent last):
{history_text or '(no history)'}

Current user question: {current_question}

Instructions for the optimized query:
- RULE 1 (MANDATORY): The primary test name / subject from the PREVIOUS question MUST appear as the first term in the optimized query. Never drop it.
- RULE 2: Append the new intent keywords from the current question after the preserved subject.
- RULE 3: Return ONE phrase (<= 12 words), no commas or lists, spaces allowed only.
- RULE 4: Language must match the user's current question language.

Examples:
- Prev: "請問 Pressure test 有幾種測試?"  New: "我要知道測試力量"
  Optimized: "Pressure test 測試力量 數值"
- Prev: "What are ESD test steps?"  New: "limit"
  Optimized: "ESD test limit values"
- Prev: "shock test 測試標準"  New: "那關機測試標準呢"
  BAD:  "關機測試 標準"          ← dropped "shock test", WRONG
  GOOD: "shock test 關機條件 標準" ← kept subject, CORRECT
- Prev: "vibration test procedure"  New: "pass criteria?"
  Optimized: "vibration test pass criteria"

Return JSON strictly following the schema.
"""

    raw = _chat_with_ollama(
        [{"role": "user", "content": prompt}],
        response_format=FOLLOWUP_INTENT_SCHEMA,
    )
    payload = _safe_json_loads(raw)
    return {
        "is_followup": bool(payload.get("is_followup")),
        "needs_new_search": bool(payload.get("needs_new_search", True)),
        "optimized_query": payload.get("optimized_query", current_question),
        "search_keywords": payload.get("search_keywords", current_question),
        "reasoning": payload.get("reasoning", ""),
    }


def generate_suggested_questions(context: str, answered_question: str) -> List[str]:
    excerpt = context[:500]
    prompt = f"""
你是文件問答系統要提供延伸問題建議。請根據以下已回答的問題與摘要內容，再提供 3 個可追問的問題。

原始問題：{answered_question}
回答摘要：{excerpt}

請只回傳 JSON 陣列格式，如：
["問題 1","問題 2","問題 3"]
"""
    raw = _chat_with_ollama(
        [{"role": "user", "content": prompt}],
        response_format=SUGGESTED_QUESTION_SCHEMA,
    )
    parsed = _safe_json_loads(raw)
    if isinstance(parsed, list):
        return [str(item) for item in parsed[:3]]
    return []


def generate_fallback_answer(question: str) -> str:
    prompt = f"""
你是一個沒有文件可查詢的助理，需要用常識回答使用者問題。
如果問題無法確定答案，請提出建議的查詢方向。

問題：{question}
"""
    return _chat_with_ollama([
        {"role": "system", "content": "請以繁體中文（台灣）作答，嚴格禁止簡體中文。避免輸出控制標記或思考過程。"},
        {"role": "user", "content": prompt},
    ])


def extract_text_with_vision(
    image_bytes_list: List[bytes],
    page_numbers: List[int],
) -> List[Dict[str, Any]]:
    """Use VL model to extract text from PDF page images, preserving layout structure.

    Returns a list of segment dicts compatible with split_segments_into_chunks.
    """
    if not image_bytes_list:
        return []

    client = get_client()
    segments = []

    def _align14(img_bytes: bytes) -> bytes:
        """Resize image so both dimensions are multiples of 14 (qwen2.5vl patch size)."""
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = img.size
        new_w = max(14, ((w + 13) // 14) * 14)
        new_h = max(14, ((h + 13) // 14) * 14)
        if new_w != w or new_h != h:
            img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    prompt = (
        "Extract ALL text from this PDF page exactly as it appears.\n"
        "Rules:\n"
        "- Preserve the original structure: indentation, line breaks, and hierarchy.\n"
        "- For tables, clearly show which values belong to which row/column label.\n"
        "  Example: 'Parameter | Condition A | Condition B'\n"
        "           'Value X   | 100 units   | 200 units'\n"
        "- For lists with sub-items, use indentation to show the relationship.\n"
        "- Output ONLY the extracted text. No explanations, no comments.\n"
        "- If the page contains images or diagrams, briefly describe them in [brackets]."
    )

    for img_bytes, page_num in zip(image_bytes_list, page_numbers):
        try:
            img_bytes = _align14(img_bytes)
            image_b64 = base64.b64encode(img_bytes).decode("utf-8")
            raw = client.chat(
                [
                    {"role": "system", "content": "You are a precise document text extractor."},
                    {"role": "user", "content": prompt, "images": [image_b64]},
                ],
                model=settings.OLLAMA_VISION_MODEL,
            )
            text = raw.strip() if raw else ""
            if text:
                segments.append({
                    "page": page_num,
                    "paragraph_index": 0,
                    "text": text,
                })
            logger.info("VL extract page=%d text_len=%d", page_num, len(text))
        except Exception as exc:
            logger.warning("VL extract page=%d failed, skipping: %s", page_num, exc)

    return segments


def analyze_pdf_page_images_singleturn(
    image_bytes_list: List[bytes],
    page_numbers: List[int],
    question: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Single-turn vision analysis that flattens history into the current prompt.

    This mirrors the stable RAG behavior to avoid reasoning-only responses on
    the first follow-up. It sends a two-message chat (system + user with images)
    and does not include prior turns as chat messages; instead it embeds recent
    Q/A text into the user prompt.
    """
    if not image_bytes_list:
        raise ValueError("no page images provided")

    images = [base64.b64encode(img).decode("utf-8") for img in image_bytes_list]
    page_label = ", ".join(map(str, page_numbers))
    user_prompt = (question or "Summarize the key points from these pages.").strip()

    # Build short textual history (last 3 turns) and concise system rules
    history_text = "\n".join(
        f"Q: {turn.get('question','')}\nA: {turn.get('answer','')}\n" for turn in (conversation_history or [])[-3:]
    )

    system_rules = (
        "You are a helpful technical assistant for analyzing documents. Your answers must be in Traditional Chinese (Taiwan).\n"
        "- Strictly NO Simplified Chinese characters.\n"
        "- Analyze the provided images and answer the user's question based *only* on the content of the images.\n"
        "- If the images contain tables, charts, or diagrams, describe them in detail.\n"
        "- Provide a comprehensive and detailed answer.\n"
        "- Use bullet points for clarity when appropriate.\n"
        "- Do not output control tokens or any internal thoughts.\n"
        "- If the information in the images is insufficient to answer the question, clearly state what is missing in Traditional Chinese.\n"
    )

    composed = (
        "Context (previous conversation, for reference only):\n"
        f"{history_text or '(none)'}\n\n"
        "Based on the provided images, perform the following task:\n"
        f"- For the document pages ({page_label}), answer this question: {user_prompt}\n\n"
        "Final Answer (in Traditional Chinese):\n"
    )

    messages = [
        {"role": "system", "content": system_rules},
        {"role": "user", "content": composed, "images": images},
    ]

    return _chat_with_ollama(
        messages,
        model=settings.OLLAMA_VISION_MODEL or settings.OLLAMA_LLM_MODEL,
    )


def analyze_pdf_page_images_stream(
    image_bytes_list: List[bytes],
    page_numbers: List[int],
    question: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
):
    """Streamed version of single-turn analysis.

    Yields dicts: {"type": "thinking"|"content", "text": "..."}
    """
    if not image_bytes_list:
        raise ValueError("no page images provided")

    client = get_client()
    images = [base64.b64encode(img).decode("utf-8") for img in image_bytes_list]
    page_label = ", ".join(map(str, page_numbers))
    user_prompt = (question or "Summarize the key points from these pages.").strip()

    history_text = "\n".join(
        f"Q: {turn.get('question','')}\nA: {turn.get('answer','')}\n" for turn in (conversation_history or [])[-3:]
    )

    system_rules = (
        "您是專業的文件分析助理，請使用流暢自然的繁體中文（台灣）回答。\n"
        "任務目標：\n"
        "1. 仔細閱讀圖片中的文字與圖表。\n"
        "2. 針對使用者的問題提供精確、重點式的回答。\n"
        "3. 若遇到表格或數據，請整理為清晰的條列式重點。\n"
        "4. 保持語句通順，避免贅字或重複詞彙。\n"
        "5. 除非必要，否則直接回答問題，不需過多開場白。\n"
    )

    composed = (
        "上下文 (參考用):\n"
        f"{history_text or '(無)'}\n\n"
        "任務指令:\n"
        f"請根據圖片內容 (頁碼: {page_label})，回答以下問題：\n"
        f"{user_prompt}\n\n"
        "回答 (繁體中文):"
    )

    messages = [
        {"role": "system", "content": system_rules},
        {"role": "user", "content": composed, "images": images},
    ]

    for delta in client.chat_stream(messages, model=settings.OLLAMA_VISION_MODEL or settings.OLLAMA_LLM_MODEL):
        yield delta


def finalize_text_answer(notes: str, question: Optional[str] = None) -> str:
    """Turn noisy notes/thinking into a clean final answer (text-only).

    Used as a post-stream rescue when the model streamed only thinking or
    extremely short content. This mirrors RAG's single-turn text generation.
    """
    if not notes:
        notes = "(no notes)"

    system = (
        "You are a helpful technical assistant. Convert the following noisy notes "
        "into a concise final answer.\n"
        "Rules:\n"
        "- Output final answer only. MUST use Traditional Chinese (繁體中文) for all Chinese text.\n"
        "- NO Simplified Chinese allowed.\n"
        "- Bullet points preferred, no control tokens, no chain-of-thought.\n"
        "- If insufficient info, state what is missing.\n"
    )
    task = (
        (f"Question: {question}\n" if question else "") +
        "Notes:\n" + notes.strip() + "\n\n" +
        "Final answer (bulleted if applicable):"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]
    return _chat_with_ollama(messages, model=settings.OLLAMA_LLM_MODEL)

def analyze_pdf_page_images(
    image_bytes_list: List[bytes],
    page_numbers: List[int],
    question: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    if not image_bytes_list:
        raise ValueError("沒有可用的頁面圖片")

    messages = _prepare_history(conversation_history)
    user_prompt = question or "請描述這些頁面中的重點內容。"

    images = [base64.b64encode(img).decode("utf-8") for img in image_bytes_list]
    page_label = ", ".join(map(str, page_numbers))
    try:
        logger.info(
            "Vision analyze: pages=%s images=%d question_len=%d history_turns=%d",
            page_numbers,
            len(images),
            len(user_prompt or ""),
            len(conversation_history or [])
        )
    except Exception:
        pass
    messages.append(
        {
            "role": "user",
            "content": (
                "以下圖片為 PDF 內容的截圖，可能與實際頁碼或視窗顯示不同步。"
                f"請僅根據影像中的文字與圖表回答問題，忽略任何頁碼差異。"
                f"當前對應的頁面標記：{page_label}。請回答：{user_prompt}"
            ),
            "images": images,
        }
    )

    # Add system guidance as the first turn to reduce repetition and keep outputs concise
    system_rules = (
        "您是專業的文件分析助理，請使用流暢自然的繁體中文（台灣）回答。\n"
        "任務目標：\n"
        "1. 仔細閱讀圖片中的文字與圖表。\n"
        "2. 針對使用者的問題提供精確、重點式的回答。\n"
        "3. 若遇到表格或數據，請整理為清晰的條列式重點。\n"
        "4. 保持語句通順，避免贅字或重複詞彙。\n"
    )
    messages.insert(0, {"role": "system", "content": system_rules})

    return _chat_with_ollama(
        messages,
        model=settings.OLLAMA_VISION_MODEL or settings.OLLAMA_LLM_MODEL,
    )
