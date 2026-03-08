"""
VLM backend abstraction — Strategy pattern.

Unifies vLLM, Gemini, and OpenAI behind a single ``VLMService`` interface.
API keys come from ``config.Settings`` (environment variables), never hardcoded.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from PIL import Image

from config.settings import VLMSettings
from core.image_utils import image_to_base64

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class VLMBackend(ABC):
    """Base class for VLM backends."""

    @abstractmethod
    def ocr(self, image: Image.Image, prompt: str, system_prompt: str = "") -> str:
        """Send an image + prompt to the VLM and return the text response."""

    @abstractmethod
    def text_only(self, prompt: str, system_prompt: str = "") -> str:
        """Send a text-only prompt (no image)."""


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------

class VLLMBackend(VLMBackend):
    """Local vLLM server via OpenAI-compatible API."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120):
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._timeout = timeout

    def ocr(self, image: Image.Image, prompt: str, system_prompt: str = "") -> str:
        data_uri = image_to_base64(image)
        messages = self._build_messages(prompt, system_prompt, data_uri)
        return self._call(messages, max_tokens=6000, temperature=0.7)

    def text_only(self, prompt: str, system_prompt: str = "") -> str:
        messages = self._build_messages(prompt, system_prompt)
        return self._call(messages, max_tokens=1024, temperature=0.0)

    # -- helpers --

    def _build_messages(self, prompt, sys_prompt, data_uri=None):
        msgs = []
        if sys_prompt:
            msgs.append({"role": "system", "content": sys_prompt})
        content = [{"type": "text", "text": prompt}]
        if data_uri:
            content.append({"type": "image_url", "image_url": {"url": data_uri}})
        msgs.append({"role": "user", "content": content})
        return msgs

    def _call(self, messages, *, max_tokens, temperature):
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=self._timeout,
        )
        return resp.choices[0].message.content.strip()


class GeminiBackend(VLMBackend):
    """Google Gemini via the ``google-genai`` SDK (chat API)."""

    def __init__(self, api_key: str, model: str, timeout: int = 120):
        try:
            from google import genai

            self._client = genai.Client(api_key=api_key)
            self._model = model
            self._timeout = timeout
        except ImportError:
            raise ImportError("Install google-genai: pip install google-genai")

    def ocr(self, image: Image.Image, prompt: str, system_prompt: str = "") -> str:
        from google.genai import types

        contents = [image, prompt]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            max_output_tokens=6000,
            temperature=0.7,
        )
        resp = self._client.models.generate_content(
            model=self._model, contents=contents, config=config
        )
        return resp.text.strip()

    def text_only(self, prompt: str, system_prompt: str = "") -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            max_output_tokens=1024,
            temperature=0.0,
        )
        resp = self._client.models.generate_content(
            model=self._model, contents=[prompt], config=config
        )
        return resp.text.strip()


class OpenAIBackend(VLLMBackend):
    """OpenAI GPT-4o etc. — same wire format as vLLM."""

    def __init__(self, api_key: str, model: str, timeout: int = 120):
        super().__init__(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            model=model,
            timeout=timeout,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class VLMService:
    """Facade that selects the configured backend and exposes ``ocr`` / ``text_only``."""

    def __init__(self, settings: Optional[VLMSettings] = None, timeout: int = 120) -> None:
        cfg = settings or VLMSettings()
        self._backend = self._create_backend(cfg, timeout)
        self._backend_name = cfg.backend
        logger.info("VLMService initialised with backend=%s", cfg.backend)

    @classmethod
    def from_settings(cls, settings: VLMSettings) -> "VLMService":
        """Factory: create from a VLMSettings object."""
        return cls(settings=settings)

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @staticmethod
    def _create_backend(cfg: VLMSettings, timeout: int) -> VLMBackend:
        if cfg.backend == "vllm":
            return VLLMBackend(cfg.vllm_base_url, cfg.vllm_api_key, cfg.vllm_model_name, timeout)
        if cfg.backend == "gemini":
            if not cfg.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not set")
            return GeminiBackend(cfg.gemini_api_key, cfg.gemini_model_name, timeout)
        if cfg.backend == "openai":
            if not cfg.openai_api_key:
                raise ValueError("OPENAI_API_KEY not set")
            return OpenAIBackend(cfg.openai_api_key, cfg.openai_model_name, timeout)
        raise ValueError(f"Unknown VLM backend: {cfg.backend}")

    # -- Public interface (delegates to backend) --

    def ocr(self, image: Image.Image, prompt: str, system_prompt: str = "") -> str:
        return self._backend.ocr(image, prompt, system_prompt)

    def text_only(self, prompt: str, system_prompt: str = "") -> str:
        return self._backend.text_only(prompt, system_prompt)


# ---------------------------------------------------------------------------
# Default prompts (centralised — no more copypaste between files)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_OCR = (
    "你是一個專業的中文手寫文字識別模型。"
    "請嚴格按照指令行為，不要輸出任何額外的說明或格式。"
    "你的任務是從圖片中識別中文手寫文字，並按照從左到右的順序輸出結果。"
    "只輸出文字本身，不要包含解釋或其他內容。"
)

USER_PROMPT_OCR = (
    "請識別這張圖片中的繁體中文手寫文字，按照從左到右的順序輸出，只要文字本身。"
    "如果有英文，請自行校正書寫方向並識別；如果有數字，請自行校正書寫方向並識別。"
    "如果有標點符號，有可能為直式書寫的格式，請嘗試識別並一律輸出全形符號，"
    "例如逗號請輸出「，」，句號請輸出「。」。不要輸出任何其他內容。"
)
