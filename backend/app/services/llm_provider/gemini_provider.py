"""
Gemini / Google AI Studio implementation of LLMProvider.

Uses the official `google-generativeai` SDK. Model IDs follow Google's naming
(e.g. "gemini-2.5-flash", "gemma-3-27b-it") and are not normalized. If you
specify an Ollama-style tag like "gemma4:e2b" against this provider, the API
will return a 404 — that's a config error, not a runtime bug.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


def _lazy_import():
    """Import google.generativeai only when this provider is actually used."""
    try:
        import google.generativeai as genai  # type: ignore
        return genai
    except ImportError as e:
        raise RuntimeError(
            "google-generativeai not installed — run `uv add google-generativeai` "
            "or switch LLM_PROVIDER back to 'ollama'."
        ) from e


def _to_genai_messages(messages: List[Dict[str, Any]]) -> tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Split out system message and convert remaining role/content pairs into
    Gemini's [{role: user|model, parts: [str]}] format.
    """
    system: Optional[str] = None
    history: List[Dict[str, Any]] = []
    for msg in messages:
        role = (msg.get("role") or "").lower()
        content = msg.get("content") or ""
        if role == "system":
            system = (system + "\n\n" + content) if system else content
            continue
        gemini_role = "user" if role == "user" else "model"
        history.append({"role": gemini_role, "parts": [content]})
    return system, history


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "gemini-2.5-flash",
        embed_model: str = "text-embedding-004",
        timeout: int = 120,
    ):
        if not api_key:
            raise ValueError("Gemini provider requires GEMINI_API_KEY")
        self._api_key = api_key
        self._default_model = default_model
        self._embed_model = embed_model
        self._timeout = timeout
        genai = _lazy_import()
        genai.configure(api_key=api_key)
        self._genai = genai

    def _get_model(self, model: Optional[str], system_instruction: Optional[str] = None):
        return self._genai.GenerativeModel(
            model or self._default_model,
            system_instruction=system_instruction,
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        format: Optional[Any] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        system, history = _to_genai_messages(messages)
        gm = self._get_model(model, system_instruction=system)
        # Pull last user turn as the "send" payload, rest as history
        if history and history[-1]["role"] == "user":
            send_parts = history[-1]["parts"]
            prior = history[:-1]
        else:
            send_parts = [""]
            prior = history

        config: Dict[str, Any] = {}
        if format == "json":
            config["response_mime_type"] = "application/json"
        if options:
            for k_src, k_dst in (
                ("temperature", "temperature"),
                ("top_p", "top_p"),
                ("top_k", "top_k"),
                ("num_predict", "max_output_tokens"),
            ):
                if k_src in options and options[k_src] is not None:
                    config[k_dst] = options[k_src]

        chat = gm.start_chat(history=prior)
        try:
            resp = chat.send_message(
                send_parts,
                generation_config=config or None,
                request_options={"timeout": self._timeout},
            )
        except Exception as e:
            logger.error("Gemini chat error: %s", e)
            raise RuntimeError(f"Gemini API 錯誤：{e}") from e
        return (resp.text or "").strip()

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, str]]:
        system, history = _to_genai_messages(messages)
        gm = self._get_model(model, system_instruction=system)
        if history and history[-1]["role"] == "user":
            send_parts = history[-1]["parts"]
            prior = history[:-1]
        else:
            send_parts = [""]
            prior = history
        chat = gm.start_chat(history=prior)
        try:
            stream = chat.send_message(send_parts, stream=True)
            for chunk in stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield {"type": "content", "text": text}
        except Exception as e:
            logger.error("Gemini stream error: %s", e)
            raise RuntimeError(f"Gemini stream 錯誤：{e}") from e

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        images: Optional[List[str]] = None,
        system: Optional[str] = None,
        format: Optional[Any] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        gm = self._get_model(model, system_instruction=system)
        parts: List[Any] = [prompt] if prompt else []
        if images:
            # images expected as base64 strings (same shape as Ollama API)
            import base64
            for b64 in images:
                try:
                    raw = base64.b64decode(b64)
                    parts.append({"mime_type": "image/jpeg", "data": raw})
                except Exception:
                    continue

        config: Dict[str, Any] = {}
        if format == "json":
            config["response_mime_type"] = "application/json"
        if options:
            for k_src, k_dst in (
                ("temperature", "temperature"),
                ("top_p", "top_p"),
                ("top_k", "top_k"),
                ("num_predict", "max_output_tokens"),
            ):
                if k_src in options and options[k_src] is not None:
                    config[k_dst] = options[k_src]

        try:
            resp = gm.generate_content(parts, generation_config=config or None)
        except Exception as e:
            logger.error("Gemini generate error: %s", e)
            raise RuntimeError(f"Gemini API 錯誤：{e}") from e
        return (resp.text or "").strip()

    def embed(
        self,
        inputs: List[str],
        *,
        model: Optional[str] = None,
    ) -> List[List[float]]:
        out: List[List[float]] = []
        target = model or self._embed_model
        for text in inputs:
            try:
                resp = self._genai.embed_content(
                    model=target,
                    content=(text or "")[:8000],
                    task_type="retrieval_document",
                )
            except Exception as e:
                logger.error("Gemini embed error: %s", e)
                raise RuntimeError(f"Gemini embed 錯誤：{e}") from e
            out.append(resp["embedding"])
        return out

    def list_models(self) -> List[Dict[str, Any]]:
        try:
            return [{"name": m.name} for m in self._genai.list_models()]
        except Exception as e:
            logger.warning("Gemini list_models failed: %s", e)
            return []

    def version(self) -> Optional[str]:
        return "gemini-api"
