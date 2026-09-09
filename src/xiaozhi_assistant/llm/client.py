from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from ..config import load_settings
from ..secrets_store import get_api_key
from ..performance import mark_api_call


class AIError(RuntimeError):
    pass


class AIClient:
    """Unified OpenAI-compatible adapter with latency-safe fallback behavior."""

    def __init__(self, *, timeout_seconds: float | None = None, max_retries: int = 0) -> None:
        settings = load_settings().ai
        key = get_api_key()
        if not key:
            raise AIError("尚未配置 API Key，请打开小智电脑助手设置。")
        if not settings.base_url or not settings.model:
            raise AIError("API Base URL 或模型名称为空，请先完成设置。")
        self.settings = settings
        self.client = OpenAI(
            api_key=key,
            base_url=settings.base_url.rstrip("/"),
            timeout=timeout_seconds if timeout_seconds is not None else settings.timeout_seconds,
            max_retries=max_retries,
        )

    def _is_official_openai(self) -> bool:
        try:
            host = (urlparse(self.settings.base_url).hostname or "").lower()
        except Exception:
            return False
        return host == "api.openai.com" or host.endswith(".openai.com")

    def _auto_order(self) -> tuple[str, str]:
        return ("responses", "chat") if self._is_official_openai() else ("chat", "responses")

    @staticmethod
    def _should_try_fallback(exc: Exception) -> bool:
        """Fallback only for fast protocol incompatibility, never after network/time/rate errors.

        Old behavior tried the second protocol after *every* failure. A 45-120 second
        timeout could therefore happen twice, which looked like the app had frozen.
        """
        text = str(exc).lower()
        hard_stop = (
            "timeout", "timed out", "connection", "connect error", "network",
            "401", "403", "unauthorized", "forbidden", "429", "rate limit",
            "quota", "insufficient", "api key",
        )
        if any(k in text for k in hard_stop):
            return False
        compat = (
            "404", "405", "not found", "unsupported", "not supported",
            "unknown endpoint", "unknown route", "not implemented", "responses api",
            "chat completions", "unrecognized request", "invalid endpoint",
        )
        return any(k in text for k in compat)

    def complete(self, prompt: str, system: str = "你是专业、可靠的中文办公助手。", max_output_tokens: int = 8192) -> str:
        mode = self.settings.api_mode
        if mode == "responses":
            try:
                return self._responses(prompt, system, max_output_tokens)
            except Exception as exc:
                raise AIError(f"Responses API: {exc}") from exc
        if mode == "chat":
            try:
                return self._chat(prompt, system, max_output_tokens)
            except Exception as exc:
                raise AIError(f"Chat Completions: {exc}") from exc

        first, second = self._auto_order()
        try:
            return self._responses(prompt, system, max_output_tokens) if first == "responses" else self._chat(prompt, system, max_output_tokens)
        except Exception as first_exc:
            if not self._should_try_fallback(first_exc):
                label = "Responses API" if first == "responses" else "Chat Completions"
                raise AIError(f"{label}: {first_exc}") from first_exc
            try:
                return self._responses(prompt, system, max_output_tokens) if second == "responses" else self._chat(prompt, system, max_output_tokens)
            except Exception as second_exc:
                raise AIError(f"AI 调用失败：{first}: {first_exc} | {second}: {second_exc}") from second_exc

    def _responses(self, prompt: str, system: str, max_output_tokens: int) -> str:
        mark_api_call()
        response = self.client.responses.create(
            model=self.settings.model,
            instructions=system,
            input=prompt,
            max_output_tokens=max_output_tokens,
        )
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()
        data = response.model_dump() if hasattr(response, "model_dump") else {}
        chunks: list[str] = []
        for item in data.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(str(content["text"]))
        if chunks:
            return "\n".join(chunks).strip()
        raise AIError("模型返回为空。")

    def _chat(self, prompt: str, system: str, max_output_tokens: int) -> str:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_output_tokens,
        }
        if self.settings.temperature is not None:
            kwargs["temperature"] = self.settings.temperature
        try:
            mark_api_call()
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if "temperature" in str(exc).lower():
                kwargs.pop("temperature", None)
                mark_api_call()
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise AIError("模型返回为空。")
        return str(content).strip()

    def complete_with_image(self, image_path: str | Path, question: str) -> str:
        path = Path(image_path)
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        data_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        mark_api_call()
        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            max_tokens=4096,
        )
        if not response.choices or not response.choices[0].message.content:
            raise AIError("当前模型没有返回图像分析结果，可能不支持视觉输入。")
        return str(response.choices[0].message.content).strip()

    def test(self) -> str:
        answer = self.complete("只回复：连接成功", system="你是 API 连通性测试助手。", max_output_tokens=32)
        return answer[:200]


def json_for_ai(value: Any, max_chars: int = 24000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[已截断]"
    return text
