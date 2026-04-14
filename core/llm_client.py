"""
LLM 客户端 — 封装 OpenAI 兼容 API 调用。

提供统一的重试、回退、模型选择能力。所有需要调用 LLM 的模块
（GeneralizationEngine、SemanticVerifier、SafetyVerifier）都通过
本客户端进行 API 调用。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM 客户端。

    公共接口：
      - chat(messages, model, temperature, max_tokens) -> str
      - chat_json(messages, model, temperature) -> Dict
    """

    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self._model = model
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._client: Optional[OpenAI] = None
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """返回累计 API 调用次数。"""
        return self._call_count

    # ---- 公共方法 --------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> str:
        """
        发送聊天请求并返回文本响应。

        参数:
            messages: OpenAI 格式的消息列表
            model: 模型名称（覆盖默认模型）
            temperature: 生成温度
            max_tokens: 最大 token 数

        返回:
            LLM 生成的文本响应

        异常:
            RuntimeError: 重试耗尽后仍然失败
        """
        use_model = model or self._model
        return self._call_with_retry(messages, use_model, temperature, max_tokens)

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回 JSON 响应。

        自动在 system prompt 中添加 JSON 输出格式要求，
        并解析响应为 Python 字典。

        参数:
            messages: OpenAI 格式的消息列表
            model: 模型名称
            temperature: 生成温度

        返回:
            解析后的 JSON 字典

        异常:
            RuntimeError: 重试耗尽后仍然失败
            json.JSONDecodeError: 响应无法解析为 JSON
        """
        # 在消息中注入 JSON 输出要求
        json_messages = list(messages)
        if json_messages and json_messages[0]["role"] == "system":
            json_messages[0] = {
                "role": "system",
                "content": json_messages[0]["content"]
                + "\n\n请严格以 JSON 格式输出结果，不要包含任何其他文本。",
            }
        else:
            json_messages.insert(0, {
                "role": "system",
                "content": "请严格以 JSON 格式输出结果，不要包含任何其他文本。",
            })

        raw = self.chat(json_messages, model=model, temperature=temperature, max_tokens=2000)
        return self._extract_json(raw)

    # ---- 内部方法 --------------------------------------------------------

    def _get_client(self) -> OpenAI:
        """延迟初始化 OpenAI 客户端。"""
        if self._client is None:
            self._client = OpenAI()
        return self._client

    def _call_with_retry(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """带重试的 API 调用（指数退避）。"""
        client = self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._call_count += 1
                content = response.choices[0].message.content or ""
                logger.debug(
                    "LLM 调用成功 (model=%s, attempt=%d, tokens=%s)",
                    model, attempt,
                    getattr(response.usage, "total_tokens", "N/A"),
                )
                return content.strip()
            except Exception as e:
                last_error = e
                wait = self._retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "LLM 调用失败 (attempt=%d/%d, model=%s): %s — 等待 %.1fs 后重试",
                    attempt, self._max_retries, model, e, wait,
                )
                time.sleep(wait)

        raise RuntimeError(
            f"LLM 调用在 {self._max_retries} 次重试后仍然失败: {last_error}"
        )

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从 LLM 响应文本中提取 JSON 对象。"""
        # 尝试直接解析
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试提取第一个 { ... } 块
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # 尝试提取第一个 [ ... ] 块（数组）
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return {"items": parsed}
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError(
            f"无法从 LLM 响应中提取 JSON: {text[:200]}...", text, 0
        )
