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
- Use spec_lookup BEFORE spec_references / spec_supersedes_chain to resolve canonical_id.
- If a tool returns no relevant info, try another tool or a different query — do NOT \
hallucinate spec content. If the corpus truly lacks info, say so in final_answer.
- Stop and emit final_answer as soon as you have enough evidence. Do not call \
extra tools for completeness; brevity is preferred.
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
