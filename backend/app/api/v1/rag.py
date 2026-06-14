import os
import json
import re
from typing import Dict, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ... import models, schemas
from ...core.config import settings
from ...core.security import get_current_user
from ...database import get_db
from ...services import ai, pdf_image, hybrid_search, rerank
from ...services.system_config import SystemConfigService


router = APIRouter()


def _project_matches(metadata: Dict[str, object], project_id: str) -> bool:
    value = (metadata or {}).get("project_id")
    if value is None:
        return False
    if isinstance(value, list):
        return project_id in value
    return value == project_id


def _join_dedup(a: str, b: str, max_overlap: int = 400) -> str:
    """串接 a+b，並裁掉 a 結尾與 b 開頭重複的部分（相鄰塊本來就有 overlap）。"""
    if not a:
        return b
    if not b:
        return a
    limit = min(len(a), len(b), max_overlap)
    for k in range(limit, 20, -1):
        if a[-k:] == b[:k]:
            return a + b[k:]
    return a + "\n" + b


def _expand_chunk_text(db: Session, chunk, *, radius: int, max_chars: int) -> str:
    """小找大：回傳「命中塊 + 同文件前後 radius 塊」合併去重後的完整上下文。

    搜尋精度仍用小塊（向量比對的是命中塊），但餵給 LLM 的是補上鄰塊的大塊，
    避免句子/數值被切塊邊界截斷（如「允收標準：」與「1.5G RMS」被切成兩塊）。
    """
    base = chunk.text or ""
    if radius <= 0:
        return base
    rows = (
        db.query(models.DocumentChunk)
        .filter(
            models.DocumentChunk.document_id == chunk.document_id,
            models.DocumentChunk.chunk_index >= chunk.chunk_index - radius,
            models.DocumentChunk.chunk_index <= chunk.chunk_index + radius,
        )
        .order_by(models.DocumentChunk.chunk_index)
        .all()
    )
    if len(rows) <= 1:
        return base
    merged = ""
    for r in rows:
        merged = _join_dedup(merged, r.text or "")
        if len(merged) >= max_chars:
            break
    return merged[:max_chars]


def _context_text_budgeted(db: Session, chunk, ctx_used: int) -> str:
    """在「總 context 預算」內做鄰塊擴展；預算用完就退回原始小塊，避免超過 num_ctx。"""
    base = chunk.text or ""
    radius = getattr(settings, "RAG_NEIGHBOR_RADIUS", 1)
    per_cap = getattr(settings, "RAG_EXPAND_MAX_CHARS", 2000)
    total_budget = ai.effective_rag_budget()
    remaining = total_budget - ctx_used
    if radius <= 0 or remaining <= len(base):
        return base
    return _expand_chunk_text(db, chunk, radius=radius, max_chars=min(per_cap, remaining))


_PAGE_GAP = 5


def _context_keep_ids(filtered):
    """智慧頁距過濾 + 塌縮保護：回傳應納入 LLM context 的 chunk id 集合。

    原本固定的頁距過濾（離主命中 ±5 頁）在「主命中是離群/索引頁，或命中本來就分散」時，
    會把 context 塌縮到極少甚至只剩 1 塊（例如最高分命中落在修訂紀錄頁，真正內容頁全被丟掉）。
    這裡只在「多數命中本來就集中在主命中附近」時才套用；否則（分散/離群）不套用、全部納入。
    """
    if not filtered:
        return set()
    primary = filtered[0][0]
    pp = primary.page or 0
    pid = primary.document_id

    def _near(c):
        if c.document_id != pid or not pp or not c.page:
            return True
        return abs(c.page - pp) <= _PAGE_GAP

    near_ids = {c.id for c, _ in filtered if _near(c)}
    if len(near_ids) >= max(2, (len(filtered) + 1) // 2):
        base = near_ids  # 命中集中 → 套用頁距過濾，維持單主題一致性
    else:
        base = {c.id for c, _ in filtered}  # 命中分散/主命中離群 → 不過濾，全部納入

    # 餵進 LLM 的塊數上限：依排序取前 N，避免分散的 hybrid 命中塞爆/破碎 context 導致生成退化。
    # 超出的塊仍會出現在 sources（前端可預覽），只是不進 LLM。
    cap = getattr(settings, "RAG_MAX_CONTEXT_CHUNKS", 6)
    ordered_kept = [c.id for c, _ in filtered if c.id in base][:cap]
    return set(ordered_kept)


def _hybrid_filtered(db, payload, search_query, embedding, vector_config, top_k):
    """混合檢索（向量 + BM25，RRF 融合）後，套用文件/分類/專案/資料夾過濾，回傳 [(chunk, score)]。

    與舊純向量流程相容：回傳的 tuple 形狀不變，下游 page-gap / context 完全沿用。
    關鍵差異：keyword-only 命中（向量相似度低於門檻但關鍵字命中）不被向量門檻砍掉，
    這正是把「靠關鍵字才找得到的分散子項目」撈回來的機制。
    """
    candidate_k = top_k * vector_config["search_multiplier"]
    fused, kw_hits = hybrid_search.fuse(db, search_query, embedding, candidate_k)
    if not fused:
        return []

    faiss_ids = [fid for fid, _ in fused]
    chunk_rows = (
        db.query(models.DocumentChunk)
        .join(models.Document, models.DocumentChunk.document_id == models.Document.id)
        .filter(models.DocumentChunk.faiss_id.in_(faiss_ids))
        .all()
    )
    chunk_map = {c.faiss_id: c for c in chunk_rows}
    min_sim = vector_config["min_similarity_score"]

    # 撈寬：先收集一個較大的候選池（供 rerank 精選），rerank 關閉時退回只收 top_k。
    rerank_on = getattr(settings, "RAG_RERANK", True)
    pool_size = max(top_k, getattr(settings, "RAG_RERANK_POOL", 12)) if rerank_on else top_k

    pool = []
    seen_pages = set()  # 同頁去重：保留 RRF 最高的那一塊，避免重複頁稀釋 context
    for fid, vscore in fused:
        chunk = chunk_map.get(fid)
        if not chunk:
            continue
        # 相關性門檻：向量低分「且非關鍵字命中」才丟棄；keyword-only 命中放行
        if vscore is not None and vscore < min_sim and fid not in kw_hits:
            continue
        doc = chunk.document
        if payload.document_id and doc.id != payload.document_id:
            continue
        if payload.classification_id and doc.classification_id != payload.classification_id:
            continue
        if payload.project_id and not _project_matches(doc.metadata_data or {}, payload.project_id):
            continue
        if payload.folder_ids and doc.folder_id not in payload.folder_ids:
            continue
        page_key = (doc.id, chunk.page)
        if chunk.page is not None and page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        # 顯示用分數：有向量分用向量分；keyword-only 命中以 0.0 佔位（前端仍可預覽內容）
        pool.append((chunk, vscore if vscore is not None else 0.0))
        if len(pool) >= pool_size:
            break

    if not rerank_on or len(pool) <= 1:
        return pool[:top_k]
    # 撈寬再精選：把垃圾頁踢掉、乾淨規格段排前，再取 top_k
    return rerank.rerank(search_query, pool, top_k)


@router.post("/query", response_model=schemas.RAGQueryResponse)
def query_rag(
    payload: schemas.RAGQueryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="問題不可為空")

    config_service = SystemConfigService(db)
    vector_config = config_service.get_vector_config()

    if payload.use_ai_fallback:
        fallback_answer = ai.generate_fallback_answer(question)
        return schemas.RAGQueryResponse(
            answer=fallback_answer, sources=[], used_ai_fallback=True
        )

    followup_analysis = None
    search_query = question
    is_followup = False
    optimized_query = None

    if payload.conversation_history and not payload.skip_ai_understanding:
        history = [
            {"question": m.question, "answer": m.answer}
            for m in payload.conversation_history
        ]
        followup_analysis = ai.analyze_followup_intent(question, history)
        is_followup = bool(followup_analysis.get("is_followup", False))
        needs_new_search = bool(followup_analysis.get("needs_new_search", True))
        optimized_query = followup_analysis.get("optimized_query", question) or question

        # 單一精簡查詢；強制與原始語言一致
        search_query = optimized_query
        has_cn = bool(re.search(r"[\u4e00-\u9fff]", question))
        has_cn_opt = bool(re.search(r"[\u4e00-\u9fff]", optimized_query))
        if (has_cn and not has_cn_opt) or (not has_cn and has_cn_opt):
            search_query = question

        # Always re-search with optimized_query for accurate follow-up results

    embeddings = ai.embed_texts([search_query])
    if not embeddings:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="嵌入計算失敗")

    filtered = _hybrid_filtered(
        db, payload, search_query, embeddings[0], vector_config, payload.top_k
    )
    if not filtered:
        return schemas.RAGQueryResponse(answer="找不到符合的內容，請調整關鍵詞或過濾條件", sources=[])

    # 頁距過濾（智慧 + 塌縮保護）：命中集中才套用；分散/主命中離群則全納入。
    primary_page = filtered[0][0].page or 0
    keep_ids = _context_keep_ids(filtered)

    contexts: List[Dict[str, str]] = []
    sources: List[schemas.DocumentChunkSource] = []
    ctx_used = 0
    for chunk, score in filtered:
        doc = chunk.document
        chunk_page = chunk.page or 0
        page_gap = abs(chunk_page - primary_page) if primary_page and chunk_page else None

        source_num = len(sources) + 1  # 1-based index matching frontend display order
        sources.append(
            schemas.DocumentChunkSource(
                document_id=doc.id,
                title=doc.title,
                page=chunk.page,
                snippet=chunk.text,
                score=score,
            )
        )

        if chunk.id not in keep_ids:
            # 加入 sources 讓前端顯示，但不傳入 LLM context
            continue

        text = _context_text_budgeted(db, chunk, ctx_used)
        ctx_used += len(text)
        contexts.append({
            "source_num": source_num,
            "title": doc.title,
            "page": chunk_page,
            "page_gap": page_gap,
            "text": text,
        })

    final_question = optimized_query or question
    history = (
        [{"question": m.question, "answer": m.answer} for m in payload.conversation_history]
        if payload.conversation_history else None
    )
    rag_prompts = config_service.get_rag_prompts()
    answer = ai.generate_rag_answer(
        final_question, contexts, conversation_history=history,
        system_prompt=rag_prompts["system_prompt"],
        user_template=rag_prompts["user_template"],
    )
    return schemas.RAGQueryResponse(
        answer=answer,
        sources=sources,
        is_followup=is_followup,
        optimized_query=optimized_query,
        suggested_questions=[],
    )


@router.post("/query/stream")
def query_stream(
    payload: schemas.RAGQueryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """與 /query 相同的檢索邏輯，但以 SSE 串流回傳思考過程與答案。"""
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="問題不可為空白")

    config_service = SystemConfigService(db)
    vector_config = config_service.get_vector_config()

    is_followup = False
    optimized_query = None
    if payload.conversation_history and not payload.skip_ai_understanding:
        try:
            history_dicts = [{"question": m.question, "answer": m.answer} for m in payload.conversation_history]
            intent = ai.analyze_followup_intent(question, history_dicts)
            is_followup = bool(intent.get("is_followup", False))
            optimized_query = intent.get("optimized_query") or question
        except Exception:
            optimized_query = question
    else:
        optimized_query = question

    search_query = optimized_query or question
    has_cn = bool(re.search(r"[\u4e00-\u9fff]", question))
    has_cn_opt = bool(re.search(r"[\u4e00-\u9fff]", search_query))
    if (has_cn and not has_cn_opt) or (not has_cn and has_cn_opt):
        search_query = question

    embeddings = ai.embed_texts([search_query])
    if not embeddings:
        def _embed_error():
            yield f"data: {json.dumps({'type': 'error', 'message': '嵌入計算失敗'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_embed_error(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    top_k = payload.top_k or 5
    filtered = _hybrid_filtered(
        db, payload, search_query, embeddings[0], vector_config, top_k
    )

    if not filtered:
        def _no_match():
            yield f"data: {json.dumps({'type': 'content', 'text': '找不到符合的內容，請調整關鍵詞或過濾條件'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': [], 'is_followup': is_followup, 'optimized_query': optimized_query}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_no_match(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    primary_page = filtered[0][0].page or 0
    keep_ids = _context_keep_ids(filtered)

    contexts: List[Dict[str, str]] = []
    sources: List[schemas.DocumentChunkSource] = []
    ctx_used = 0
    for chunk, score in filtered:
        doc = chunk.document
        chunk_page = chunk.page or 0
        page_gap = abs(chunk_page - primary_page) if primary_page and chunk_page else None
        source_num = len(sources) + 1
        sources.append(schemas.DocumentChunkSource(
            document_id=doc.id, title=doc.title, page=chunk.page,
            snippet=chunk.text, score=score,
        ))
        if chunk.id not in keep_ids:
            continue
        text = _context_text_budgeted(db, chunk, ctx_used)
        ctx_used += len(text)
        contexts.append({
            "source_num": source_num, "title": doc.title, "page": chunk_page, "page_gap": page_gap,
            "text": text,
        })

    final_question = optimized_query or question
    history = (
        [{"question": m.question, "answer": m.answer} for m in payload.conversation_history]
        if payload.conversation_history else None
    )
    sources_data = [s.model_dump() for s in sources]
    rag_prompts = config_service.get_rag_prompts()

    def generate():
        try:
            if not contexts:
                yield f"data: {json.dumps({'type': 'content', 'text': '查無足夠的相關內容，請提供更多文件或調整問題。'}, ensure_ascii=False)}\n\n"
            else:
                for stream_chunk in ai.generate_rag_answer_stream(
                    final_question, contexts, conversation_history=history,
                    system_prompt=rag_prompts["system_prompt"],
                    user_template=rag_prompts["user_template"],
                ):
                    yield f"data: {json.dumps(stream_chunk, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data, 'is_followup': is_followup, 'optimized_query': optimized_query}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_event(event: str, data: Dict[str, str]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/analyze-pdf-pages", response_model=schemas.PdfPageAnalysisResponse)
async def analyze_pdf_pages(
    payload: schemas.PdfPageAnalysisRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    document = db.query(models.Document).filter(models.Document.id == payload.document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    if not document.pdf_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="此文件沒有可用的 PDF")

    pdf_full_path = document.pdf_path
    if not os.path.exists(pdf_full_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF 檔案不存在")

    total_pages = pdf_image.get_pdf_page_count(pdf_full_path)
    invalid = [p for p in payload.page_numbers if p < 1 or p > total_pages]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"頁碼 {invalid} 超出文件總頁數 {total_pages}",
        )

    unique_pages = list(dict.fromkeys(payload.page_numbers))
    if len(unique_pages) > settings.MAX_PDF_ANALYSIS_PAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多分析 {settings.MAX_PDF_ANALYSIS_PAGES} 頁，請減少頁數後重試",
        )
    if len(unique_pages) > 1:
        image_bytes_list = pdf_image.pdf_pages_to_images(pdf_full_path, unique_pages, dpi=100, max_dimension=1024)
    else:
        image_bytes_list = pdf_image.pdf_pages_to_images(pdf_full_path, unique_pages)
    history = (
        [{"question": m.question, "answer": m.answer} for m in payload.conversation_history]
        if payload.conversation_history
        else None
    )
    answer = ai.analyze_pdf_page_images_singleturn(
        image_bytes_list=image_bytes_list,
        page_numbers=unique_pages,
        question=payload.question,
        conversation_history=history,
    )
    return schemas.PdfPageAnalysisResponse(
        answer=answer, page_numbers=unique_pages, document_title=document.title or ""
    )


@router.post("/analyze-pdf-pages/stream")
def analyze_pdf_pages_stream(
    payload: schemas.PdfPageAnalysisRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    document = db.query(models.Document).filter(models.Document.id == payload.document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    if not document.pdf_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="此文件沒有可用的 PDF")

    pdf_full_path = document.pdf_path
    if not os.path.exists(pdf_full_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF 檔案不存在")

    total_pages = pdf_image.get_pdf_page_count(pdf_full_path)
    invalid = [p for p in payload.page_numbers if p < 1 or p > total_pages]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"頁碼 {invalid} 超出文件總頁數 {total_pages}",
        )

    unique_pages = list(dict.fromkeys(payload.page_numbers))
    if len(unique_pages) > settings.MAX_PDF_ANALYSIS_PAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多分析 {settings.MAX_PDF_ANALYSIS_PAGES} 頁，請減少頁數後重試",
        )
    # 多頁分析降低解析度避免 context overflow；單頁維持原始高解析度
    if len(unique_pages) > 1:
        image_bytes_list = pdf_image.pdf_pages_to_images(pdf_full_path, unique_pages, dpi=100, max_dimension=1024)
    else:
        image_bytes_list = pdf_image.pdf_pages_to_images(pdf_full_path, unique_pages)
    history = (
        [{"question": m.question, "answer": m.answer} for m in payload.conversation_history]
        if payload.conversation_history
        else None
    )

    def event_gen():
        try:
            content_accum: List[str] = []
            thinking_accum: List[str] = []
            for delta in ai.analyze_pdf_page_images_stream(
                image_bytes_list=image_bytes_list,
                page_numbers=unique_pages,
                question=payload.question,
                conversation_history=history,
            ):
                if not isinstance(delta, dict):
                    continue
                t = delta.get("type")
                text = delta.get("text") or ""
                if not text:
                    continue
                if t == "thinking":
                    thinking_accum.append(text)
                    yield _sse_event("thinking", {"text": text})
                else:
                    content_accum.append(text)
                    yield _sse_event("content", {"text": text})

            final_content = "".join(content_accum).strip()
            if len(final_content) < 20:
                notes = "".join(thinking_accum).strip()
                if notes:
                    final_answer = ai.finalize_text_answer(notes, payload.question)
                    if final_answer and final_answer.strip():
                        final_content = final_answer
                        yield _sse_event("content", {"text": final_answer})
            
            # Save conversation history to per-user DB table
            try:
                question_label = payload.question
                if not question_label:
                    if len(unique_pages) == 1:
                        question_label = f"請分析第 {unique_pages[0]} 頁的重點內容"
                    else:
                        question_label = f"請分析第 {', '.join(map(str, unique_pages))} 頁的整體內容"

                new_entry = {
                    "question": question_label,
                    "answer": final_content,
                    "page_numbers": unique_pages,
                    "timestamp": str(datetime.now()),
                }

                row = db.query(models.DocumentUserAnalysis).filter(
                    models.DocumentUserAnalysis.document_id == payload.document_id,
                    models.DocumentUserAnalysis.user_id == current_user.id,
                ).first()
                if row:
                    from sqlalchemy.orm.attributes import flag_modified
                    row.messages = row.messages + [new_entry]
                    flag_modified(row, "messages")
                else:
                    row = models.DocumentUserAnalysis(
                        document_id=payload.document_id,
                        user_id=current_user.id,
                        messages=[new_entry],
                    )
                    db.add(row)
                db.commit()
            except Exception as db_err:
                print(f"Failed to save conversation history: {db_err}")
                # Don't fail the stream for DB error, just log it

        except Exception as e:
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ===== Per-user conversation history =====

@router.get("/config")
def get_rag_config(current_user=Depends(get_current_user)):
    """回傳前端需要的 RAG 相關設定值"""
    return {"max_pdf_analysis_pages": settings.MAX_PDF_ANALYSIS_PAGES}


@router.get("/conversation")
def get_conversation(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """取得當前使用者的對話紀錄"""
    row = db.query(models.UserConversation).filter(
        models.UserConversation.user_id == current_user.id
    ).first()
    return {"messages": row.messages if row else []}


@router.put("/conversation")
def save_conversation(
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """儲存當前使用者的對話紀錄"""
    messages = payload.get("messages", [])
    row = db.query(models.UserConversation).filter(
        models.UserConversation.user_id == current_user.id
    ).first()
    if row:
        row.messages = messages
    else:
        row = models.UserConversation(user_id=current_user.id, messages=messages)
        db.add(row)
    db.commit()
    return {"ok": True}


@router.delete("/conversation", status_code=204)
def clear_conversation(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """清除當前使用者的對話紀錄"""
    db.query(models.UserConversation).filter(
        models.UserConversation.user_id == current_user.id
    ).delete()
    db.commit()
    return None

