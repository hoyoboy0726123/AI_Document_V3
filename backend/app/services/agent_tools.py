"""
Tool registry exposed to the Agent. Each tool has:
  - name: stable identifier used in tool-call JSON
  - description: shown to the LLM in system prompt
  - schema: input parameter shape (Pydantic-like dict, not full Pydantic to keep prompt short)
  - run(db, params) -> dict: executes the tool, returns observation

Tools are intentionally narrow — they wrap KG service / RAG search / docs lookup.
The LLM never sees raw SQL.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models
from ..core.config import settings
from . import ai, hybrid_search, kg_service, rerank

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    name: str
    description: str
    schema: Dict[str, Any]  # JSON schema-ish; rendered into prompt
    run: Callable[[Session, Dict[str, Any]], Dict[str, Any]]


# ───── Tool implementations ────────────────────────────────────────────────


def _tool_rag_search(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    top_k = int(params.get("top_k") or 5)
    top_k = max(1, min(top_k, 10))

    embeddings = ai.embed_texts([query])
    if not embeddings:
        return {"error": "embedding failed"}

    # 與 RAG /query 一致：向量 + BM25 RRF 融合 → cross-encoder 精選。
    # （Agent 為全域搜尋，不做 document/分類過濾。）
    candidate_k = top_k * 4
    fused, kw_hits = hybrid_search.fuse(db, query, embeddings[0], candidate_k)
    if not fused:
        return {"results": []}

    faiss_ids = [fid for fid, _ in fused]
    chunk_rows = (
        db.query(models.DocumentChunk)
        .join(models.Document, models.DocumentChunk.document_id == models.Document.id)
        .filter(models.DocumentChunk.faiss_id.in_(faiss_ids))
        .all()
    )
    chunk_map = {c.faiss_id: c for c in chunk_rows}

    min_sim = 0.25
    rerank_on = getattr(settings, "RAG_RERANK", True)
    pool_size = max(top_k, getattr(settings, "RAG_RERANK_POOL", 12)) if rerank_on else top_k

    pool: List[tuple] = []
    seen_pages = set()
    for fid, vscore in fused:
        chunk = chunk_map.get(fid)
        if not chunk:
            continue
        # keyword-only 命中放行；向量低分且非關鍵字命中才丟棄
        if vscore is not None and vscore < min_sim and fid not in kw_hits:
            continue
        doc = chunk.document
        page_key = (doc.id, chunk.page)
        if chunk.page is not None and page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        pool.append((chunk, vscore if vscore is not None else 0.0))
        if len(pool) >= pool_size:
            break

    selected = rerank.rerank(query, pool, top_k) if (rerank_on and len(pool) > 1) else pool[:top_k]

    out: List[Dict[str, Any]] = []
    for chunk, score in selected:
        doc = chunk.document
        out.append({
            "document_id": doc.id,
            "title": doc.title,
            "page": chunk.page,
            "score": round(score, 4),
            # 放寬截斷：snippet 同時用於 ReAct 推理與最後的 grounded 合成引用
            "snippet": (chunk.text or "")[:1400],
        })
    return {"results": out}


def _tool_spec_lookup(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    name = str(params.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    rows = kg_service.search_entities(db, name, limit=10)
    return {
        "results": [
            {
                "id": r.id,
                "canonical_id": r.canonical_id,
                "type": r.type,
                "description": r.description,
            }
            for r in rows
        ]
    }


def _resolve_entity(db: Session, key: str) -> Optional[models.KGEntity]:
    if not key:
        return None
    row = db.query(models.KGEntity).filter_by(id=key).first()
    if row:
        return row
    return db.query(models.KGEntity).filter_by(canonical_id=key).first()


def _tool_spec_references(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    key = str(params.get("spec_id") or params.get("entity_id") or params.get("canonical_id") or "").strip()
    ent = _resolve_entity(db, key)
    if not ent:
        return {"error": f"entity not found: {key}"}

    hops = int(params.get("hops") or 1)
    nodes, edges = kg_service.get_neighbors(db, ent.id, hops=hops)
    node_map = {n.id: n for n in nodes}

    out_refs: List[Dict[str, Any]] = []
    in_refs: List[Dict[str, Any]] = []
    for e in edges:
        if e.src_id == ent.id and e.dst_id != ent.id:
            other = node_map.get(e.dst_id)
            if other:
                out_refs.append({
                    "canonical_id": other.canonical_id,
                    "type": other.type,
                    "rel_type": e.rel_type,
                    "confidence": e.confidence,
                })
        elif e.dst_id == ent.id and e.src_id != ent.id:
            other = node_map.get(e.src_id)
            if other:
                in_refs.append({
                    "canonical_id": other.canonical_id,
                    "type": other.type,
                    "rel_type": e.rel_type,
                    "confidence": e.confidence,
                })
    return {
        "center": ent.canonical_id,
        "type": ent.type,
        "outgoing": out_refs,  # this spec references these
        "incoming": in_refs,   # these specs reference this one
    }


def _tool_spec_supersedes_chain(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    key = str(params.get("spec_id") or params.get("entity_id") or params.get("canonical_id") or "").strip()
    ent = _resolve_entity(db, key)
    if not ent:
        return {"error": f"entity not found: {key}"}
    chain = kg_service.get_supersedes_chain(db, ent.id)
    return {
        "chain": [
            {"canonical_id": e.canonical_id, "type": e.type, "is_center": e.id == ent.id}
            for e in chain
        ]
    }


def _tool_document_get(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    doc_id = str(params.get("doc_id") or params.get("document_id") or "").strip()
    if not doc_id:
        return {"error": "doc_id is required"}
    doc = db.query(models.Document).filter_by(id=doc_id).first()
    if not doc:
        return {"error": "document not found"}
    return {
        "id": doc.id,
        "title": doc.title,
        "ai_summary": (doc.ai_summary or "")[:1000],
        "classification": doc.classification.name if doc.classification else None,
        "metadata": doc.metadata_data or {},
        "page_count": (
            db.query(models.DocumentChunk).filter_by(document_id=doc.id).count()
        ),
    }


def _natural_key(number):
    """'12.10' 排在 '12.2' 之後（自然排序）。"""
    try:
        return [int(p) for p in str(number or "").split(".") if p != ""]
    except Exception:
        return [0]


def _tool_list_subitems(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    """列出某文件/測試/章節的子項目（KG 結構：contains / part_of）。列舉題用這個，不要用 rag_search。"""
    name = str(params.get("name") or params.get("query") or "").strip()
    if not name:
        return {"error": "name is required"}
    rows = kg_service.search_entities(db, name, limit=10)
    if not rows:
        # 反向比對：LLM 常傳整句（如「ASUS NB 測試計畫中的 Pressure Test」）。
        # 找「實體名稱出現在查詢字串內」的結構節點，取最長(最具體)者。
        ql = name.lower()
        cand = db.query(models.KGEntity).filter(models.KGEntity.type.in_(["section", "document"])).all()
        rows = sorted(
            [e for e in cand if e.name and len(e.name) >= 3 and e.name.lower() in ql],
            key=lambda e: len(e.name or ""),
            reverse=True,
        )[:10]
    if not rows:
        return {"matched": None, "subitems": [], "hint": "KG 無對應節點；改用 rag_search"}

    q = name.lower()

    def _score(e) -> int:
        nm = (e.name or "").lower()
        s = 10 if e.type in ("section", "document") else 0
        if nm == q:
            s += 5
        elif q in nm or nm in q:
            s += 2
        return s

    ent = sorted(rows, key=_score, reverse=True)[0]

    # 子項目 = 出向 contains（文件→章節）+ 入向 part_of（子→母）
    child_ids: List[str] = [
        r.dst_id for r in db.query(models.KGRelation).filter_by(src_id=ent.id, rel_type="contains").all()
    ] + [
        r.src_id for r in db.query(models.KGRelation).filter_by(dst_id=ent.id, rel_type="part_of").all()
    ]
    subitems: List[Dict[str, Any]] = []
    if child_ids:
        emap = {e.id: e for e in db.query(models.KGEntity).filter(models.KGEntity.id.in_(child_ids)).all()}
        seen: set = set()
        for cid in child_ids:
            if cid in seen:
                continue
            seen.add(cid)
            c = emap.get(cid)
            if c:
                meta = c.meta or {}
                subitems.append({
                    "name": c.name,
                    "kind": meta.get("kind") or c.type,
                    "number": meta.get("number"),
                    "page": meta.get("page"),
                    "document_id": meta.get("document_id"),
                })
        subitems.sort(key=lambda x: _natural_key(x.get("number")))

    # 該節點引用的標準
    refs: List[str] = []
    for r in db.query(models.KGRelation).filter_by(src_id=ent.id, rel_type="references").all():
        t = db.query(models.KGEntity).filter_by(id=r.dst_id).first()
        if t:
            refs.append(t.canonical_id)

    return {
        "matched": ent.name,
        "kind": (ent.meta or {}).get("kind") or ent.type,
        "subitems": subitems[:60],
        "subitem_count": len(subitems),
        "references": refs,
    }


def _resolve_named_structural(db: Session, name: str):
    """名稱 → 結構節點：先 forward 子字串搜尋，再 reverse-containment（名稱出現在查詢字串內）。"""
    rows = kg_service.search_entities(db, name, limit=10)
    if not rows:
        ql = name.lower()
        cand = db.query(models.KGEntity).filter(models.KGEntity.type.in_(["section", "document"])).all()
        rows = sorted(
            [e for e in cand if e.name and len(e.name) >= 3 and e.name.lower() in ql],
            key=lambda e: len(e.name or ""), reverse=True,
        )[:10]
    if not rows:
        return None
    q = name.lower()

    def _score(e) -> int:
        nm = (e.name or "").lower()
        s = 10 if e.type in ("section", "document") else 0
        if nm == q:
            s += 5
        elif q in nm or nm in q:
            s += 2
        return s

    return sorted(rows, key=_score, reverse=True)[0]


_ASPECT_KW = {
    "criteria": ["criteria", "criterion", "判定", "驗收", "合格"],
    "specification": ["specification", "規格", "spec"],
    "objective": ["objective", "目的", "purpose"],
}


def _tool_get_subitem_details(db: Session, params: Dict[str, Any]) -> Dict[str, Any]:
    """逐項抓細節：對某父節點的每個子項目，分別抓出它自己的 criteria/spec/objective 段落。

    用於「這些測試的判定標準各是什麼」這類『細節橫跨多個子項目』的問題 —— top-k 檢索抓不齊，
    這裡用 KG 已知的每個子項目頁碼，逐一精準定位各自段落，保證全部涵蓋。
    """
    name = str(params.get("name") or params.get("query") or "").strip()
    aspect = str(params.get("aspect") or "criteria").strip().lower()
    if aspect not in _ASPECT_KW:
        aspect = "criteria"
    if not name:
        return {"error": "name is required"}
    ent = _resolve_named_structural(db, name)
    if not ent:
        return {"matched": None, "items": [], "hint": "KG 無對應節點"}

    child_ids = [
        r.dst_id for r in db.query(models.KGRelation).filter_by(src_id=ent.id, rel_type="contains").all()
    ] + [
        r.src_id for r in db.query(models.KGRelation).filter_by(dst_id=ent.id, rel_type="part_of").all()
    ]
    children = db.query(models.KGEntity).filter(models.KGEntity.id.in_(child_ids)).all() if child_ids else []
    # 葉節點（無子項目，如「Shock Test」）→ 取它自己的段落；有子項目 → 逐項取。
    is_leaf = not children
    targets = [ent] if is_leaf else children
    phrase = {"criteria": "Testing Criteria", "specification": "Testing Specification", "objective": "Testing Objective"}[aspect]
    kw = _ASPECT_KW[aspect]

    # 本文件所有 section 的頁碼（排序），用來算每個 target 的「下一節」邊界（章節常跨頁，用節邊界較準）。
    doc_id0 = (ent.meta or {}).get("document_id")
    all_pages = sorted({
        (e.meta or {}).get("page")
        for e in db.query(models.KGEntity).filter(models.KGEntity.type == "section").all()
        if (e.meta or {}).get("document_id") == doc_id0 and (e.meta or {}).get("page")
    })

    def _next_section_page(p):
        return next((x for x in all_pages if x > p), None)

    items: List[Dict[str, Any]] = []
    for c in sorted(targets, key=lambda e: ((e.meta or {}).get("page") or 0, _natural_key((e.meta or {}).get("number")))):
        meta = c.meta or {}
        doc_id, page = meta.get("document_id"), meta.get("page")
        detail = None
        if doc_id and page:
            next_page = _next_section_page(page)
            hi = (next_page - 1) if (next_page and next_page > page) else (page + 6)
            chunks = (
                db.query(models.DocumentChunk)
                .filter(
                    models.DocumentChunk.document_id == doc_id,
                    models.DocumentChunk.page >= page,
                    models.DocumentChunk.page <= hi,
                )
                .order_by(models.DocumentChunk.page, models.DocumentChunk.chunk_index)
                .all()
            )
            joined = "\n".join(ch.text or "" for ch in chunks)
            low = joined.lower()
            number = meta.get("number")
            ph = r"\s+".join(re.escape(w) for w in phrase.split())  # 對空白寬鬆，如 Testing\s+Criteria
            pos = -1
            # 1) 最精準：用「本項編號 + 子節 + 小節名」定位（如 "12.6.7 Testing Criteria"），
            #    避免抓到鄰項或下一個 section（最後一項範圍較寬時尤其重要）。
            if number:
                matches = list(re.finditer(re.escape(str(number)) + r"\.\d+\s*" + ph, joined, re.IGNORECASE))
                if matches:
                    m = matches[-1]  # 頁面內容偶有重複（前者常為誤抽），取最後一個實質段落
                    pm = re.search(ph, joined[m.start():], re.IGNORECASE)
                    pos = m.start() + (pm.start() if pm else 0)
            # 2) 退而求其次：第一次出現的小節名。
            if pos < 0:
                m = re.search(ph, joined, re.IGNORECASE)
                pos = m.start() if m else -1
            # 3) 最後用關鍵字。
            if pos < 0:
                for k in kw:
                    i = low.find(k.lower())
                    if i >= 0:
                        pos = i
                        break
            if pos >= 0:
                # 在「完整內文」中找下一個小節標題作為邊界（不是固定小視窗），
                # 這樣同一小節跨頁的後續內容（如 12.1 spec 的 Operation 部分）也會完整帶出。
                # 邊界只認「下一個子節標題」(Testing X)，不要把頁尾 Copyright 當邊界——
                # 因為頁尾會出現在小節中間的換頁處，誤當邊界會把後續(如 Operation 規格)整段切掉。
                tail = re.search(
                    r"(?:\d+(?:\.\d+){1,2}\s*)?"  # 一併切掉子節前的編號（如 12.1.8）
                    r"Testing\s+(?:Result|Objective|Specification|Procedure|Location|Criteria|Software|Equipment|Method)",
                    joined[pos + len(phrase):], re.IGNORECASE,
                )
                end = (pos + len(phrase) + tail.start()) if tail else (pos + 3500)
                seg = joined[pos:end]
                # 清掉頁尾/頁碼雜訊（把跨頁切斷的內容接回）。
                seg = re.sub(r"\s*Copyright\s*\d{4}[^\n]*", " ", seg, flags=re.IGNORECASE)
                seg = re.sub(r"\s*ASUS NB System Reliability[^\n]*", " ", seg, flags=re.IGNORECASE)
                seg = re.sub(r"\s*Page\s*\d+\b", " ", seg, flags=re.IGNORECASE)
                # 去除因抽取重複造成的相鄰重複行。
                seen_lines, deduped = set(), []
                for ln in seg.splitlines():
                    key = ln.strip()
                    if key and key in seen_lines:
                        continue
                    if key:
                        seen_lines.add(key)
                    deduped.append(ln)
                detail = "\n".join(deduped).strip()[:2400]
            elif joined:
                detail = joined[:600].strip()
        items.append({
            "name": c.name, "number": meta.get("number"),
            "page": page, "document_id": doc_id, "detail": detail,
        })
    return {"matched": ent.name, "aspect": aspect, "items": items, "item_count": len(items), "is_leaf": is_leaf}


# ───── Registry ───────────────────────────────────────────────────────────


TOOLS: Dict[str, Tool] = {
    "rag_search": Tool(
        name="rag_search",
        description=(
            "Vector search across all ingested documents. Use for free-text "
            "queries about content (e.g. 'humidity test conditions')."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "natural language search query"},
                "top_k": {"type": "integer", "description": "max results (1-10, default 5)"},
            },
            "required": ["query"],
        },
        run=_tool_rag_search,
    ),
    "spec_lookup": Tool(
        name="spec_lookup",
        description=(
            "Find specification entities by name or partial ID (e.g. 'ISO 9001', 'MIL-STD-810'). "
            "Returns the canonical_id you'll pass to spec_references / spec_supersedes_chain."
        ),
        schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        run=_tool_spec_lookup,
    ),
    "spec_references": Tool(
        name="spec_references",
        description=(
            "Given a spec canonical_id, return what it references (outgoing) and what "
            "references it (incoming). Use this to follow cross-references between specs."
        ),
        schema={
            "type": "object",
            "properties": {
                "spec_id": {"type": "string", "description": "canonical_id e.g. 'MIL-STD-810G'"},
                "hops": {"type": "integer", "description": "1-3 hops (default 1)"},
            },
            "required": ["spec_id"],
        },
        run=_tool_spec_references,
    ),
    "spec_supersedes_chain": Tool(
        name="spec_supersedes_chain",
        description=(
            "Trace the version chain of a spec — older versions it supersedes "
            "and newer versions that supersede it. Returns chain oldest→newest."
        ),
        schema={
            "type": "object",
            "properties": {"spec_id": {"type": "string"}},
            "required": ["spec_id"],
        },
        run=_tool_spec_supersedes_chain,
    ),
    "document_get": Tool(
        name="document_get",
        description="Fetch document metadata (title, summary, classification, page count) by ID.",
        schema={
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
        run=_tool_document_get,
    ),
    "list_subitems": Tool(
        name="list_subitems",
        description=(
            "List the COMPLETE set of sub-items / child sections of a document, test, or "
            "section BY NAME, from the knowledge-graph structure (contains / part_of). "
            "USE THIS — not rag_search — for enumeration questions: 'what tests/items does X "
            "have', '有哪些', 'list all ...', 'sub-tests of ...', 'X 的子項目'. "
            "Returns the exact full list (rag_search would miss items). Also returns the "
            "standards that node references."
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "document title / test / section name, e.g. 'Pressure Test'"},
            },
            "required": ["name"],
        },
        run=_tool_list_subitems,
    ),
    "get_subitem_details": Tool(
        name="get_subitem_details",
        description=(
            "For a parent test/document, return EACH sub-item's specific section content for an "
            "aspect (criteria / specification / objective). USE THIS for 'what are the criteria/"
            "specs/objectives of these tests', 'X 的判定標準/規格/目的 各是什麼', i.e. a DETAIL that "
            "spans many sub-items. Locates each sub-item's own section by its KG page, so all "
            "sub-items are covered (rag_search would miss most)."
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "parent name, e.g. 'Pressure Test'"},
                "aspect": {"type": "string", "description": "criteria | specification | objective (default criteria)"},
            },
            "required": ["name"],
        },
        run=_tool_get_subitem_details,
    ),
}


def render_tools_for_prompt() -> str:
    """Render tool list for inclusion in the Agent system prompt."""
    lines: List[str] = []
    for tool in TOOLS.values():
        params = tool.schema.get("properties", {})
        param_descs = []
        for pname, pspec in params.items():
            ptype = pspec.get("type", "string")
            pdesc = pspec.get("description", "")
            required = pname in tool.schema.get("required", [])
            param_descs.append(f"    - {pname} ({ptype}{'*' if required else ''}): {pdesc}")
        params_str = "\n".join(param_descs) if param_descs else "    (no params)"
        lines.append(f"- {tool.name}: {tool.description}\n  params:\n{params_str}")
    return "\n".join(lines)


def run_tool(db: Session, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    tool = TOOLS.get(name)
    if not tool:
        return {"error": f"unknown tool: {name}. Valid: {list(TOOLS.keys())}"}
    try:
        return tool.run(db, params or {})
    except Exception as e:
        logger.warning("tool %s failed: %s", name, e, exc_info=True)
        return {"error": f"{name} failed: {e}"}
