import os
import json
import re
from typing import Dict, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ... import models, schemas
from ...core.security import get_current_user
from ...database import get_db
from ...services import ai, pdf_image, vector_store
from ...services.system_config import SystemConfigService


router = APIRouter()


def _project_matches(metadata: Dict[str, object], project_id: str) -> bool:
    value = (metadata or {}).get("project_id")
    if value is None:
        return False
    if isinstance(value, list):
        return project_id in value
    return value == project_id


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

    search_results = vector_store.search(
        embeddings[0], top_k=payload.top_k * vector_config["search_multiplier"]
    )
    if not search_results:
        return schemas.RAGQueryResponse(answer="目前無可用文件內容", sources=[])

    faiss_ids = [fid for fid, _ in search_results]
    chunk_rows = (
        db.query(models.DocumentChunk)
        .join(models.Document, models.DocumentChunk.document_id == models.Document.id)
        .filter(models.DocumentChunk.faiss_id.in_(faiss_ids))
        .all()
    )
    chunk_map = {c.faiss_id: c for c in chunk_rows}

    filtered: List[tuple[models.DocumentChunk, float]] = []
    for fid, score in search_results:
        if score < vector_config["min_similarity_score"]:
            continue
        chunk = chunk_map.get(fid)
        if not chunk:
            continue
        doc = chunk.document
        if payload.document_id and doc.id != payload.document_id:
            continue
        if payload.classification_id and doc.classification_id != payload.classification_id:
            continue
        if payload.project_id and not _project_matches(doc.metadata_data or {}, payload.project_id):
            continue
        filtered.append((chunk, score))
        if len(filtered) >= payload.top_k:
            break

    if not filtered:
        return schemas.RAGQueryResponse(answer="找不到符合的內容，請調整關鍵詞或過濾條件", sources=[])

    # 計算頁碼間距：以最高分塊（filtered[0]）的頁碼為基準
    primary_page = filtered[0][0].page or 0

    contexts: List[Dict[str, str]] = []
    sources: List[schemas.DocumentChunkSource] = []
    for chunk, score in filtered:
        doc = chunk.document
        chunk_page = chunk.page or 0
        page_gap = abs(chunk_page - primary_page) if primary_page and chunk_page else None
        contexts.append({
            "title": doc.title,
            "page": chunk_page,
            "page_gap": page_gap,
            "text": chunk.text,
        })
        sources.append(
            schemas.DocumentChunkSource(
                document_id=doc.id,
                title=doc.title,
                page=chunk.page,
                snippet=chunk.text,
                score=score,
            )
        )

    final_question = optimized_query or question
    history = (
        [{"question": m.question, "answer": m.answer} for m in payload.conversation_history]
        if payload.conversation_history else None
    )
    answer = ai.generate_rag_answer(final_question, contexts, conversation_history=history)
    return schemas.RAGQueryResponse(
        answer=answer,
        sources=sources,
        is_followup=is_followup,
        optimized_query=optimized_query,
        suggested_questions=[],
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
            
            # Save conversation history to DB
            try:
                # Refresh document to ensure we have the latest state
                db.refresh(document)
                
                current_analysis = document.full_analysis or {}
                history_list = current_analysis.get("conversation_history", [])
                
                # Determine the question label
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
                    "timestamp": str(datetime.now())
                }
                
                history_list.append(new_entry)
                current_analysis["conversation_history"] = history_list
                
                # Update and commit
                document.full_analysis = current_analysis
                # Force update for SQLAlchemy mutable dict
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(document, "full_analysis")
                
                db.add(document)
                db.commit()
            except Exception as db_err:
                print(f"Failed to save conversation history: {db_err}")
                # Don't fail the stream for DB error, just log it

        except Exception as e:
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(event_gen(), media_type="text/event-stream")

