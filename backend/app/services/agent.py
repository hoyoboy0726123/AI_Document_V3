"""
ReAct-style Agent loop.

The LLM emits JSON of one of two shapes per step:
  {"thought": "...", "action": "tool_name", "action_input": {...}}
  {"thought": "...", "final_answer": "..."}

We parse the JSON (strict), execute the tool, append observation, repeat
until final_answer or max_steps. Bad JSON gets one retry with a stricter
instruction; second failure terminates with the raw text as final answer.

Yields a stream of events for SSE consumption.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy.orm import Session

from . import agent_tools, ai
from ..core.config import settings
from .llm_provider import get_llm_provider
from .system_config import SystemConfigService

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT_TEMPLATE = """You are a precise document-research agent for a knowledge base of \
technical standards (ISO / IEC / MIL-STD / IEEE / ASTM / JIS / CNS / etc).

You answer the user's question by calling tools step-by-step. Each step you \
output ONE JSON object — no prose, no markdown fences.

Two output shapes:
  {{"thought": "<one-sentence reasoning>", "action": "<tool_name>", "action_input": {{...}}}}
  {{"thought": "<one-sentence reasoning>", "final_answer": "<answer in user's language>"}}

Available tools:
{tools}

Rules:
- Output ONE JSON object per turn, nothing else.
- Stay ANCHORED to the user's original subject. You MAY rephrase a query for better \
retrieval (drop filler words, extract keywords, add synonyms), but you must NOT switch to a \
different topic than what was asked. Retrieved snippets are EVIDENCE, not a redirection — if \
a search surfaces a similarly-named but different item, do not pivot to it. Your final_answer \
must answer the ORIGINAL question's subject.
- Use spec_lookup BEFORE spec_references / spec_supersedes_chain to resolve canonical_id.
- For enumeration / listing questions ("what items/tests does X have", "有哪些", "list all", \
"子項目", "sub-tests of X"), call list_subitems(name) FIRST. It returns the COMPLETE set from \
the knowledge graph; rag_search alone retrieves only top-k chunks and WILL miss items.
- For a question ABOUT a whole category/group ("介紹/說明 X", "tell me about the X tests", \
"these tests", "X 的內容/重點"), or a FOLLOW-UP elaborating on a group, call coverage_check(name) \
to get EVERY sub-item with content. rag_search ranks by keyword/similarity and WILL miss \
sub-items whose pages don't contain the keyword (e.g. a 'Surface Deflection' sub-test under \
'Pressure Test'). If a rag_search for a category looks partial, follow up with coverage_check \
and merge — the final answer must cover ALL sub-items, not only the ones rag_search surfaced.
- If a tool returns no relevant info, try another tool or a different query — do NOT \
hallucinate spec content. If the corpus truly lacks info, say so in final_answer.
- Stop and emit final_answer as soon as you have enough evidence. Brevity is preferred for \
SINGLE-item questions; but for category/group questions completeness wins — make sure every \
sub-item (per list_subitems / coverage_check) is represented before finishing.
- Always answer in the user's language (zh-TW if they wrote Chinese; English otherwise).
- Cite document titles or spec canonical_ids inline when summarizing findings.

Max {max_steps} steps. After that, you MUST emit final_answer."""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _parse_step(text: str) -> Optional[Dict[str, Any]]:
    """Return parsed step dict or None if no valid JSON found."""
    if not text:
        return None
    text = text.strip()

    # Try fenced code block first
    fence = _JSON_FENCE_RE.search(text)
    candidates: List[str] = []
    if fence:
        candidates.append(fence.group(1).strip())
    # Then first top-level {...} object
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group(0))

    for raw in candidates:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _build_history_messages(conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compress recent QA history into chat messages for context."""
    msgs: List[Dict[str, Any]] = []
    for entry in (conversation_history or [])[-4:]:
        q = (entry.get("question") or "").strip()
        a = (entry.get("answer") or "").strip()
        if q:
            msgs.append({"role": "user", "content": q})
        if a:
            msgs.append({"role": "assistant", "content": a[:1500]})
    return msgs


def _grounded_synthesis(
    db: Session,
    question: str,
    rag_evidence: List[Dict[str, Any]],
    kg_notes: List[str],
    conversation_history: Optional[List[Dict[str, Any]]],
) -> tuple:
    """Phase 0：用已調好的 RAG grounding prompt 重新生成最終答案。

    回傳 (answer, n_rag_used, n_rag_total_unique)，後兩者供 Phase 3 完整度反問使用。

    把 ReAct 過程蒐集到的 rag_search 命中段落（含 title/page）+ KG 關聯整理成
    編號 context，套用「只能依段落、標 [來源]、不可跨來源拼湊」的 RAG 模板再生成一次，
    讓 Agent 答案具備 RAG 等級的引用與防幻覺紀律。總長度受 num_ctx 預算限制。
    """
    budget = ai.effective_rag_budget()

    # 先去重，算出「實際有幾筆不重複的檢索證據」(total_unique)，供 Phase 3 完整度判斷
    deduped: List[tuple] = []
    seen: set = set()
    for ev in rag_evidence:
        text = (ev.get("snippet") or ev.get("text") or "").strip()
        if not text:
            continue
        key = (ev.get("document_id"), ev.get("page"), text[:80])
        if key in seen:
            continue
        seen.add(key)
        deduped.append((ev, text))
    total_unique = len(deduped)

    # 在預算內塞入 context；裝不下的就是「檢索到但未展開」的來源
    contexts: List[Dict[str, Any]] = []
    used_sources: List[Dict[str, Any]] = []  # 供前端可點/可預覽的結構化來源（對齊 RAG）
    used = 0
    for ev, text in deduped:
        if used + len(text) > budget:
            text = text[: max(0, budget - used)]
        if not text:
            break
        contexts.append({
            "source_num": len(contexts) + 1,
            "title": ev.get("title") or "",
            "page": ev.get("page"),
            "page_gap": None,
            "text": text,
        })
        used_sources.append({
            "document_id": ev.get("document_id"),
            "title": ev.get("title") or "",
            "page": ev.get("page"),
            "snippet": ev.get("snippet") or text,
            "score": ev.get("score"),
        })
        used += len(text)
        if used >= budget:
            break
    n_rag_used = len(contexts)

    # 把 KG / spec 關聯當作額外一個來源塊（若還有預算）
    if kg_notes and used < budget:
        note_text = ("關聯資訊（知識圖譜）:\n" + "\n".join(kg_notes))[: max(0, budget - used)]
        if note_text.strip():
            contexts.append({
                "source_num": len(contexts) + 1,
                "title": "知識圖譜關聯",
                "page": None,
                "page_gap": None,
                "text": note_text,
            })

    if not contexts:
        return None, [], 0, total_unique

    prompts = SystemConfigService(db).get_rag_prompts()
    answer = ai.generate_rag_answer(
        question,
        contexts,
        conversation_history=conversation_history,
        system_prompt=prompts["system_prompt"],
        user_template=prompts["user_template"],
    )
    return answer, used_sources, n_rag_used, total_unique


def _coverage_note(n_unused_sources: int, kg_edges_seen: int) -> str:
    """Phase 3：依啟發式產生「還有更多、要不要深掘」的反問（不額外呼叫 LLM）。

    只在「確實還有未展開的檢索來源或圖譜關聯」時才附加，避免每次都問。
    """
    bits: List[str] = []
    if n_unused_sources > 0:
        bits.append(f"另有約 {n_unused_sources} 段相關內容因長度限制未在本次展開")
    if kg_edges_seen > 0:
        bits.append(f"知識圖譜中已找到 {kg_edges_seen} 條規範關聯，可再往上追引用鏈／版本鏈")
    if not bits:
        return ""
    return "\n\n---\n📌 " + "；".join(bits) + "。需要我針對哪一項深入查嗎？"


_ENUM_RE = re.compile(
    r"(有哪些|哪些|列出|列舉|清單|子項目|有什麼|包含哪些|底下有|下有|"
    r"sub[- ]?items?|list all|list the|what .*(items|tests|sub)|which .*(items|tests))",
    re.IGNORECASE,
)


def _looks_like_enumeration(q: str) -> bool:
    """判斷是否為列舉題（有哪些/列出/子項目…），用於確定性 KG 列舉 fallback。"""
    return bool(_ENUM_RE.search(q or ""))


_OVERVIEW_RE = re.compile(
    r"(介紹|說明|概覽|概述|描述|重點|摘要|整理|內容|overview|brief|describe|summar|"
    r"tell me about|rundown|walk me through|各[項個種子]|每[項個種]|each\b|"
    r"all (the )?(tests|items|sub))",
    re.IGNORECASE,
)


def _looks_like_overview(q: str) -> bool:
    """判斷是否為『類別/概覽』題（介紹/說明/各項/each…）。實際是否接管仍需 KG 命中有子項的父節點。"""
    return bool(_OVERVIEW_RE.search(q or ""))


_ASPECT_RE = [
    ("criteria", re.compile(r"(判定標準|判定基準|驗收標準|合格標準|測試標準|criteria|criterion)", re.IGNORECASE)),
    ("specification", re.compile(r"(測試規格|規格|測試條件|specification|\bspec\b)", re.IGNORECASE)),
    ("objective", re.compile(r"(測試目的|目的|用途|objective)", re.IGNORECASE)),
]


def _detect_aspect(q: str) -> Optional[str]:
    """偵測『細節橫跨多項目』問題的面向：判定標準 / 規格 / 目的。"""
    for aspect, rx in _ASPECT_RE:
        if rx.search(q or ""):
            return aspect
    return None


def _group_summary(db: Session, matched: str, conversation_history) -> str:
    """對一組測試做 2~4 句摘要（自行檢索內容），供列舉題附加說明。"""
    try:
        rs = agent_tools.run_tool(db, "rag_search", {"query": matched, "top_k": 5})
        ev = rs.get("results", []) if isinstance(rs, dict) else []
        if not ev:
            return ""
        sq = (
            f"請用 2~4 句話摘要說明「{matched}」這組測試整體在測試什麼、目的為何，"
            "以段落呈現；不要再列出子項目清單。"
        )
        ans, _s, _u, _t = _grounded_synthesis(db, sq, ev, [], conversation_history)
        return ans.strip() if ans else ""
    except Exception as e:
        logger.warning("group summary failed: %s", e)
        return ""


def _try_structural_answer(db: Session, question: str, conversation_history) -> Optional[Dict[str, Any]]:
    """結構性問題快速路徑（不跑慢的 ReAct loop，直接查 KG 確定性作答）：
      - 細節橫跨多子項目（X 的判定標準/規格/目的 各是什麼）→ 逐項抓段落
      - 列舉（X 有哪些子項目）→ 完整清單 + 摘要
    回傳 {"text", "sources"} 或 None。對象名稱會從『問題 + 最近一輪歷史』解析（處理「這些測試」）。
    """
    search_text = question or ""
    if conversation_history:
        last = conversation_history[-1]
        search_text = f"{question} {last.get('question', '')} {(last.get('answer', '') or '')[:200]}"

    aspect = _detect_aspect(question)
    if aspect:
        det = agent_tools.run_tool(db, "get_subitem_details", {"name": search_text, "aspect": aspect})
        items = det.get("items") or []
        if any(it.get("detail") for it in items):
            label = {"criteria": "判定標準", "specification": "測試規格", "objective": "測試目的"}[aspect]
            is_leaf = det.get("is_leaf")
            if is_leaf:
                lines = [f"「{det.get('matched')}」的{label}如下："]
            else:
                lines = [f"「{det.get('matched')}」各子項目的{label}如下："]
            sources: List[Dict[str, Any]] = []
            for it in items:
                num, nm = it.get("number"), it.get("name")
                if not is_leaf:  # 葉節點本身就是標題，不再重複加 ### 子標題
                    lines.append(f"\n### {(str(num) + ' ') if num else ''}{nm}")
                lines.append((it.get("detail") or "（此項找不到對應段落，建議改用一般 RAG 查詢）").strip())
                if it.get("document_id"):
                    sources.append({
                        "document_id": it["document_id"], "title": nm, "page": it.get("page"),
                        "snippet": (it.get("detail") or "")[:200], "score": None,
                    })
            if not is_leaf:
                lines.append("\n（以上為逐一查找各子項目段落的結果，已涵蓋全部子項目）")
            return {"text": "\n".join(lines), "sources": sources}

    if _looks_like_enumeration(question):
        sub = agent_tools.run_tool(db, "list_subitems", {"name": search_text})
        subitems = sub.get("subitems") or []
        if subitems:
            lines = [f"「{sub.get('matched')}」共有 {len(subitems)} 個子項目："]
            sources = []
            for it in subitems:
                num, nm = it.get("number"), it.get("name")
                lines.append(f"- {(str(num) + ' ') if num else ''}{nm}")
                if it.get("document_id"):
                    sources.append({
                        "document_id": it["document_id"], "title": nm, "page": it.get("page"),
                        "snippet": f"{(str(num) + ' ') if num else ''}{nm}", "score": None,
                    })
            if sub.get("references"):
                lines.append(f"\n引用標準：{'、'.join(sub['references'])}")
            lines.append("\n（以上為知識圖譜結構的完整列舉）")
            body = "\n".join(lines)
            summary = _group_summary(db, sub.get("matched") or question, conversation_history)
            if summary:
                body += f"\n\n📝 摘要說明：\n{summary}"
            return {"text": body, "sources": sources}

    # 類別/概覽題（介紹/說明/各項…）→ 用 coverage_check 確定性涵蓋「全部子項 + 各自內容」，
    # 不依賴 RAG（會漏不含關鍵字的子項）也不依賴 LLM 自選名稱（可能誤命中同名葉節點）。
    if _looks_like_overview(question):
        cov = agent_tools.run_tool(db, "coverage_check", {"name": search_text})
        items = cov.get("items") or []
        if cov.get("matched") and not cov.get("is_leaf") and len(items) >= 2:
            lines = [f"「{cov.get('matched')}」共有 {len(items)} 個子項目，逐項內容如下："]
            sources: List[Dict[str, Any]] = []
            for it in items:
                num, nm = it.get("number"), it.get("name")
                lines.append(f"\n### {(str(num) + ' ') if num else ''}{nm}")
                ex = (it.get("excerpt") or "").strip()
                lines.append(ex if ex else "（此項找不到對應段落，建議改用一般 RAG 查詢）")
                if it.get("document_id"):
                    sources.append({
                        "document_id": it["document_id"], "title": nm, "page": it.get("page"),
                        "snippet": ex[:200], "score": None,
                    })
            lines.append("\n（以上為知識圖譜結構的完整覆蓋，已涵蓋全部子項目）")
            return {"text": "\n".join(lines), "sources": sources}

    return None


def run_agent(
    db: Session,
    question: str,
    *,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    max_steps: int = 8,
) -> Generator[Dict[str, Any], None, None]:
    """
    Yield events:
      {"type": "thought", "step": n, "text": ...}
      {"type": "tool_call", "step": n, "tool": str, "input": dict}
      {"type": "observation", "step": n, "tool": str, "output": dict}
      {"type": "final", "text": str}
      {"type": "error", "message": str}
    """
    # 快速路徑：結構性問題（列舉 / 逐項細節）直接查 KG 確定性作答，跳過慢的 ReAct loop。
    try:
        quick = _try_structural_answer(db, question, conversation_history)
    except Exception as e:
        logger.warning("structural fast-path failed: %s", e)
        quick = None
    if quick:
        yield {"type": "thought", "step": 0, "text": "偵測到結構性問題，直接查知識圖譜結構作答。"}
        yield {"type": "final", "text": quick["text"], "sources": quick.get("sources", [])}
        return

    llm = get_llm_provider()
    tools_desc = agent_tools.render_tools_for_prompt()
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(tools=tools_desc, max_steps=max_steps)

    scratchpad: List[Dict[str, Any]] = []  # alternating assistant (tool call) / user (observation)
    history_messages = _build_history_messages(conversation_history or [])

    final_text: Optional[str] = None
    # Phase 0：蒐集證據供最後 grounded 合成（rag_search 命中段落 + KG/spec 關聯）
    rag_evidence: List[Dict[str, Any]] = []
    kg_notes: List[str] = []
    kg_edges_seen = 0  # Phase 3：圖譜關聯數，供完整度反問
    structural_results: List[Dict[str, Any]] = []  # list_subitems 的權威完整清單（列舉題確定性作答）

    for step in range(1, max_steps + 1):
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history_messages,
            {"role": "user", "content": question},
        ]
        messages.extend(scratchpad)

        # Strong nudge if we're approaching the cap
        if step == max_steps:
            messages.append({
                "role": "user",
                "content": "You are at the final step. Emit final_answer JSON now.",
            })

        try:
            raw = llm.chat(messages, format="json")
        except TypeError:
            raw = llm.chat(messages)
        except Exception as e:
            logger.error("agent llm chat failed at step %d: %s", step, e)
            yield {"type": "error", "message": f"LLM 呼叫失敗：{e}"}
            return

        parsed = _parse_step(raw)
        if parsed is None:
            # one retry with stricter wording
            retry_msgs = messages + [{
                "role": "user",
                "content": (
                    "Your previous output was not valid JSON. Output a single JSON "
                    "object now matching either {thought, action, action_input} or "
                    "{thought, final_answer}. No prose, no fences."
                ),
            }]
            try:
                raw2 = llm.chat(retry_msgs, format="json")
            except TypeError:
                raw2 = llm.chat(retry_msgs)
            except Exception as e:
                yield {"type": "error", "message": f"LLM 重試失敗：{e}"}
                return
            parsed = _parse_step(raw2)
            if parsed is None:
                logger.warning("agent step %d gave no parseable JSON; using raw text", step)
                final_text = (raw or raw2 or "").strip() or "暫無足夠資訊"
                break

        thought = str(parsed.get("thought") or "").strip()
        if thought:
            yield {"type": "thought", "step": step, "text": thought}

        if "final_answer" in parsed:
            final_text = str(parsed.get("final_answer") or "").strip()
            break

        action = str(parsed.get("action") or "").strip()
        # 容錯：LLM 偶爾把工具名叫錯（get_sumerules_item_details…）→ 正規化成有效名，
        # 讓 SSE 事件、run_tool 分派、以及下方依 action 名的後處理都用同一個正確名稱。
        if action and action not in agent_tools.TOOLS:
            action = agent_tools.resolve_tool_name(action) or action
        action_input = parsed.get("action_input") or {}
        if not isinstance(action_input, dict):
            action_input = {"raw": str(action_input)}

        if not action:
            # missing action AND no final_answer — terminate with whatever we have
            final_text = thought or "暫無足夠資訊"
            break

        yield {"type": "tool_call", "step": step, "tool": action, "input": action_input}

        observation = agent_tools.run_tool(db, action, action_input)
        yield {"type": "observation", "step": step, "tool": action, "output": observation}

        # Phase 0：累積證據供最後 grounded 合成
        if isinstance(observation, dict):
            if action == "rag_search":
                for res in observation.get("results", []):
                    if isinstance(res, dict):
                        rag_evidence.append(res)
            elif action == "list_subitems" and "error" not in observation:
                # 把「完整子項目清單」當成權威證據餵進合成，避免合成只用 RAG 片段而漏項。
                items = observation.get("subitems") or []
                names = "、".join(i.get("name", "") for i in items if i.get("name"))
                cnt = observation.get("subitem_count", len(items))
                if items:
                    structural_results.append({
                        "matched": observation.get("matched"),
                        "subitems": items,
                        "references": observation.get("references") or [],
                    })
                if names:
                    kg_notes.append(f"「{observation.get('matched')}」的完整子項目（共 {cnt} 項，來自知識圖譜結構）：{names}")
                refs = observation.get("references") or []
                if refs:
                    kg_notes.append(f"「{observation.get('matched')}」引用的標準：{'、'.join(refs)}")
            elif action in ("spec_references", "spec_supersedes_chain", "spec_lookup", "document_get"):
                if "error" not in observation:
                    kg_notes.append(f"{action} → " + json.dumps(observation, ensure_ascii=False)[:900])
                    if action == "spec_references":
                        kg_edges_seen += len(observation.get("outgoing", [])) + len(observation.get("incoming", []))

        # Append to scratchpad so the LLM sees its previous tool call + result
        scratchpad.append({
            "role": "assistant",
            "content": json.dumps(parsed, ensure_ascii=False),
        })
        scratchpad.append({
            "role": "user",
            "content": (
                f"Observation from {action}:\n"
                + json.dumps(observation, ensure_ascii=False)[:6000]
            ),
        })

    if final_text is None:
        final_text = "已達最大步數，未能整合出最終答案。建議縮小問題範圍後重試。"

    # 列舉題：用 list_subitems 的權威完整清單作答（不經會漏項的 RAG 合成）。
    ql = question.lower()
    chosen = None
    for sr in structural_results:
        if (sr.get("matched") or "").lower() in ql and sr.get("subitems"):
            chosen = sr
            break
    if chosen is None and len(structural_results) == 1 and structural_results[0].get("subitems"):
        chosen = structural_results[0]
    # 確定性 fallback：即使這一輪 LLM 沒呼叫 list_subitems，列舉題仍直接從問題字串解析實體並完整列舉。
    if chosen is None and _looks_like_enumeration(question):
        fb = agent_tools.run_tool(db, "list_subitems", {"name": question})
        if isinstance(fb, dict) and fb.get("subitems"):
            chosen = {
                "matched": fb.get("matched"),
                "subitems": fb.get("subitems"),
                "references": fb.get("references") or [],
            }

    if chosen:
        lines = [f"「{chosen['matched']}」共有 {len(chosen['subitems'])} 個子項目："]
        enum_sources: List[Dict[str, Any]] = []
        for it in chosen["subitems"]:
            num = it.get("number")
            lines.append(f"- {(str(num) + ' ') if num else ''}{it.get('name', '')}")
            if it.get("document_id"):
                enum_sources.append({
                    "document_id": it.get("document_id"),
                    "title": it.get("name", ""),
                    "page": it.get("page"),
                    "snippet": f"{(str(num) + ' ') if num else ''}{it.get('name', '')}",
                    "score": None,
                })
        if chosen.get("references"):
            lines.append(f"\n引用標準：{'、'.join(chosen['references'])}")
        lines.append("\n（以上為知識圖譜結構的完整列舉）")
        body = "\n".join(lines)

        # 不只列清單：再用檢索到的內容對這組測試做摘要說明，回答「這些在測什麼」。
        # 若這一輪沒有 rag 證據（例如直接走 fallback），就主動檢索一次以確保有摘要。
        evidence_for_summary = list(rag_evidence)
        if not evidence_for_summary:
            try:
                rs = agent_tools.run_tool(db, "rag_search", {"query": chosen["matched"], "top_k": 5})
                if isinstance(rs, dict):
                    evidence_for_summary = rs.get("results", []) or []
            except Exception:
                evidence_for_summary = []
        if evidence_for_summary:
            try:
                sq = (
                    f"請用 2~4 句話摘要說明「{chosen['matched']}」這組測試整體在測試什麼、目的為何，"
                    "以段落呈現；不要再列出子項目清單。"
                )
                s_ans, _s, _u, _t = _grounded_synthesis(db, sq, evidence_for_summary, [], conversation_history)
                if s_ans and s_ans.strip():
                    body += f"\n\n📝 摘要說明：\n{s_ans.strip()}"
            except Exception as e:
                logger.warning("enumeration summary failed: %s", e)

        yield {"type": "final", "text": body, "sources": enum_sources}
        return

    # Phase 0：若過程有檢索/KG 證據，最後用 RAG grounding prompt 重新合成帶引用的答案。
    # 合成失敗或無證據時，退回 ReAct 自己的 final_answer。
    # Phase 3：合成後依啟發式判斷「還有沒有未展開的來源/關聯」，有的話在答案末尾反問。
    final_sources: List[Dict[str, Any]] = []
    if rag_evidence or kg_notes:
        try:
            grounded, final_sources, n_used, n_total = _grounded_synthesis(
                db, question, rag_evidence, kg_notes, conversation_history
            )
            if grounded and grounded.strip():
                final_text = grounded.strip()
                note = _coverage_note(max(0, n_total - n_used), kg_edges_seen)
                if note:
                    final_text += note
        except Exception as e:
            logger.warning("grounded synthesis failed, using raw final_answer: %s", e)

    yield {"type": "final", "text": final_text, "sources": final_sources}
