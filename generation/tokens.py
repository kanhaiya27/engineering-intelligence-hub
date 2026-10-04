"""
Engineering Intelligence Hub — exact prompt token counting for the local ladder
================================================================================
Ollama silently truncates a prompt that does not fit its context window
(num_ctx): the model then answers from cut-off evidence and nothing reports it.
To prevent that, prompts are counted BEFORE they are sent, with the model
family's own tokenizer and chat template.

Verified on Laptop A (2026-10-05): for the same system+user messages, this
counter and Ollama's `prompt_eval_count` agreed exactly (702 = 702) for both
qwen2.5-coder:1.5b and qwen2.5-coder:7b; the Qwen2.5-Coder sizes share one
tokenizer.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from core.logging import get_logger

logger = get_logger(__name__)

# Ollama model-name prefix -> Hugging Face tokenizer with the same vocabulary and template.
TOKENIZER_FOR_PREFIX = {
    "qwen2.5-coder:": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
}


class ChatTokenCounter:
    """Counts chat-template tokens exactly; returns None when no tokenizer is known."""

    _cache: Dict[str, object] = {}
    _lock = threading.Lock()

    @staticmethod
    def tokenizer_id(model_id: str) -> Optional[str]:
        for prefix, hf_id in TOKENIZER_FOR_PREFIX.items():
            if model_id.startswith(prefix):
                return hf_id
        return None

    def _load(self, hf_id: str):
        with self._lock:
            if hf_id not in self._cache:
                from transformers import AutoTokenizer

                self._cache[hf_id] = AutoTokenizer.from_pretrained(hf_id)
            return self._cache[hf_id]

    def count(self, model_id: str, messages: List[Dict[str, str]]) -> Optional[int]:
        hf_id = self.tokenizer_id(model_id)
        if hf_id is None:
            return None
        try:
            tok = self._load(hf_id)
            out = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=True)
        except Exception as exc:  # noqa: BLE001 - offline / missing tokenizer: caller decides
            logger.warning(f"Token counter unavailable for {model_id}: {exc}")
            return None
        ids = out["input_ids"] if hasattr(out, "keys") else out
        return len(ids)
