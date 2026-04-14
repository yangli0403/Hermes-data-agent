"""
VLM 客户端 — 封装图像理解与视觉判定调用。

负责调用多模态大模型（如 GPT-4 Vision、Gemini 等）进行图像理解、
图文一致性判断和视觉打分。输出结构化判定结果。

与 LLMClient（纯文本）和 ImageClient（图像生成）职责分离。

公共接口：
  - judge(image_path, question, expected_answer, ...) -> VLMJudgment
  - judge_consistency(image_path, statement, ...) -> VLMJudgment
  - describe(image_path, ...) -> str
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class VLMJudgment:
    """视觉判定结果。"""

    passed: bool = False
    score: float = 0.0
    reason: str = ""
    raw_evidence: str = ""
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "passed": self.passed,
            "score": self.score,
            "reason": self.reason,
            "raw_evidence": self.raw_evidence,
            "model": self.model,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# VLMClient
# ---------------------------------------------------------------------------

class VLMClient:
    """
    VLM 客户端（图像理解与视觉判定）。

    公共接口：
      - judge(image_path, question, expected_answer, threshold) -> VLMJudgment
      - judge_consistency(image_path, statement, threshold) -> VLMJudgment
      - describe(image_path, detail_level) -> str

    异常结构：
      - ValueError: 参数不合法（如图像路径不存在）
      - RuntimeError: 重试耗尽后仍然失败
      - FileNotFoundError: 图像文件不存在
    """

    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_tokens: int = 1000,
    ):
        """
        初始化 VLM 客户端。

        参数:
            model: 默认多模态模型名称
            max_retries: 最大重试次数
            retry_delay: 重试间隔基数（秒）
            max_tokens: 最大输出 token 数
        """
        self._model = model
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_tokens = max_tokens
        self._client = None
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """返回累计 API 调用次数。"""
        return self._call_count

    # ---- 公共方法 --------------------------------------------------------

    def judge(
        self,
        image_path: str,
        question: str,
        expected_answer: str,
        threshold: float = 0.7,
        model: Optional[str] = None,
    ) -> VLMJudgment:
        """
        判断图像内容是否与问答对一致。

        参数:
            image_path: 图像文件路径
            question: 视觉问题
            expected_answer: 期望答案
            threshold: 通过阈值（0.0-1.0）
            model: 模型名称（覆盖默认模型）

        返回:
            VLMJudgment 判定结果

        异常:
            FileNotFoundError: 图像文件不存在
            RuntimeError: 重试耗尽
        """
        self._validate_image_path(image_path)
        use_model = model or self._model

        system_prompt = (
            "你是一个视觉问答一致性评审员。你需要判断给定的图像是否能够支持"
            "以下问答对的正确性。\n\n"
            "请以 JSON 格式返回结果，包含以下字段：\n"
            '- "score": 0.0-1.0 的一致性分数\n'
            '- "passed": 是否通过（布尔值）\n'
            '- "reason": 判定理由\n'
            '- "evidence": 从图像中观察到的关键证据'
        )

        user_content = (
            f"问题：{question}\n"
            f"期望答案：{expected_answer}\n\n"
            f"请根据图像内容判断上述问答对是否一致。"
            f"通过阈值为 {threshold}。"
        )

        messages = self._build_vision_messages(
            system_prompt=system_prompt,
            user_text=user_content,
            image_path=image_path,
        )

        raw_response = self._call_with_retry(messages, use_model)
        return self._parse_judgment(raw_response, threshold, use_model)

    def judge_consistency(
        self,
        image_path: str,
        statement: str,
        threshold: float = 0.7,
        model: Optional[str] = None,
    ) -> VLMJudgment:
        """
        判断图像内容是否与语义陈述一致。

        参数:
            image_path: 图像文件路径
            statement: 语义陈述文本
            threshold: 通过阈值
            model: 模型名称

        返回:
            VLMJudgment 判定结果
        """
        self._validate_image_path(image_path)
        use_model = model or self._model

        system_prompt = (
            "你是一个图文一致性评审员。你需要判断给定的图像是否与"
            "以下语义陈述一致。\n\n"
            "请以 JSON 格式返回结果，包含以下字段：\n"
            '- "score": 0.0-1.0 的一致性分数\n'
            '- "passed": 是否通过（布尔值）\n'
            '- "reason": 判定理由\n'
            '- "evidence": 从图像中观察到的关键证据'
        )

        user_content = (
            f"语义陈述：{statement}\n\n"
            f"请根据图像内容判断上述陈述是否与图像一致。"
            f"通过阈值为 {threshold}。"
        )

        messages = self._build_vision_messages(
            system_prompt=system_prompt,
            user_text=user_content,
            image_path=image_path,
        )

        raw_response = self._call_with_retry(messages, use_model)
        return self._parse_judgment(raw_response, threshold, use_model)

    def describe(
        self,
        image_path: str,
        detail_level: str = "auto",
        model: Optional[str] = None,
    ) -> str:
        """
        生成图像的文本描述。

        参数:
            image_path: 图像文件路径
            detail_level: 描述详细程度（"brief"、"detailed"、"auto"）
            model: 模型名称

        返回:
            图像描述文本
        """
        self._validate_image_path(image_path)
        use_model = model or self._model

        detail_instruction = {
            "brief": "请用一句话简要描述图像内容。",
            "detailed": "请详细描述图像中的所有可见元素、场景、颜色和空间关系。",
            "auto": "请描述图像的主要内容。",
        }.get(detail_level, "请描述图像的主要内容。")

        messages = self._build_vision_messages(
            system_prompt="你是一个图像描述助手。",
            user_text=detail_instruction,
            image_path=image_path,
        )

        return self._call_with_retry(messages, use_model)

    # ---- 内部方法 --------------------------------------------------------

    def _validate_image_path(self, image_path: str) -> None:
        """校验图像文件路径。"""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图像文件不存在: {image_path}")
        if not path.is_file():
            raise ValueError(f"路径不是文件: {image_path}")

    def _build_vision_messages(
        self,
        system_prompt: str,
        user_text: str,
        image_path: str,
    ) -> List[Dict[str, Any]]:
        """构建包含图像的多模态消息。"""
        # 读取图像并编码为 base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # 推断 MIME 类型
        suffix = Path(image_path).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/png")

        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}",
                        },
                    },
                ],
            },
        ]

    def _get_client(self):
        """延迟初始化 OpenAI 客户端。"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def _call_with_retry(
        self,
        messages: List[Dict[str, Any]],
        model: str,
    ) -> str:
        """带重试的 API 调用（指数退避）。"""
        client = self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    temperature=0.3,
                )
                self._call_count += 1
                content = response.choices[0].message.content or ""
                logger.debug(
                    "VLM 调用成功 (model=%s, attempt=%d)",
                    model, attempt,
                )
                return content.strip()
            except Exception as e:
                last_error = e
                wait = self._retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "VLM 调用失败 (attempt=%d/%d, model=%s): %s — 等待 %.1fs 后重试",
                    attempt, self._max_retries, model, e, wait,
                )
                time.sleep(wait)

        raise RuntimeError(
            f"VLM 调用在 {self._max_retries} 次重试后仍然失败: {last_error}"
        )

    def _parse_judgment(
        self,
        raw_response: str,
        threshold: float,
        model: str,
    ) -> VLMJudgment:
        """解析 VLM 判定响应为 VLMJudgment 对象。"""
        try:
            # 尝试直接解析 JSON
            data = self._extract_json(raw_response)
            score = float(data.get("score", 0.0))
            passed = data.get("passed", score >= threshold)
            reason = data.get("reason", "")
            evidence = data.get("evidence", "")

            return VLMJudgment(
                passed=passed,
                score=score,
                reason=reason,
                raw_evidence=evidence,
                model=model,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("VLM 响应解析失败，使用原始文本: %s", e)
            return VLMJudgment(
                passed=False,
                score=0.0,
                reason=f"响应解析失败: {e}",
                raw_evidence=raw_response[:500],
                model=model,
            )

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从响应文本中提取 JSON 对象。"""
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

        raise json.JSONDecodeError(
            f"无法从 VLM 响应中提取 JSON: {text[:200]}...", text, 0
        )
