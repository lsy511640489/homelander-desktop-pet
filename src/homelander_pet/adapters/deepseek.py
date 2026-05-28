from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(slots=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout: float = 60.0

    @classmethod
    def from_environment(cls, base_url: str = "https://api.deepseek.com", model: str = "deepseek-chat") -> "DeepSeekConfig":
        return cls(api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(), base_url=base_url, model=model)


class DeepSeekClient:
    def __init__(self, config: DeepSeekConfig) -> None:
        self.config = config

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        if not self.config.api_key:
            raise RuntimeError("Missing DEEPSEEK_API_KEY environment variable")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = self._build_request(body)

        try:
            with request.urlopen(req, timeout=self.config.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek request failed: {exc.code} {detail}") from exc

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ):
        """Stream chat completion, yielding content chunks."""
        if not self.config.api_key:
            raise RuntimeError("Missing DEEPSEEK_API_KEY environment variable")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = self._build_request(body)

        try:
            with request.urlopen(req, timeout=self.config.timeout) as response:
                for line_bytes in response:
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek request failed: {exc.code} {detail}") from exc

    def _build_request(self, body: bytes) -> request.Request:
        return request.Request(
            self.config.base_url.rstrip("/") + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
