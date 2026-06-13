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
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models
from . import ai, kg_service, vector_store

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

    results = vector_store.search(embeddings[0], top_k=top_k * 4)
    if not results:
        return {"results": []}

    faiss_ids = [fid for fid, _ in results]
    chunk_rows = (
        db.query(models.DocumentChunk)
        .join(models.Document, models.DocumentChunk.document_id == models.Document.id)
        .filter(models.DocumentChunk.faiss_id.in_(faiss_ids))
        .all()
    )
    chunk_map = {c.faiss_id: c for c in chunk_rows}

    out: List[Dict[str, Any]] = []
    for fid, score in results:
        if score < 0.25:
            continue
        chunk = chunk_map.get(fid)
        if not chunk:
            continue
        doc = chunk.document
        out.append({
            "document_id": doc.id,
            "title": doc.title,
            "page": chunk.page,
            "score": round(score, 4),
            # 放寬截斷：snippet 同時用於 ReAct 推理與最後的 grounded 合成引用
            "snippet": (chunk.text or "")[:1400],
        })
        if len(out) >= top_k:
            break
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
