"""
文本自洽校验器 — 对 VLMSample 的文本部分执行自洽性校验。

对问题、答案、提示词与语义陈述执行文本自洽校验，确保样本在
送入视觉校验前具备基本一致性。需要调用 LLM。

公共接口：
  - verify(sample, threshold) -> StageResult
  - verify_batch(samples, threshold) -> List[StageResult]
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from core.contracts import VLMSample
from core.llm_client import LLMClient
from core.rule_verifier import StageResult

logger = logging.getLogger(__name__)


class ConsistencyVerifier:
    """
    文本自洽校验器。

    公共接口：
      - verify(sample, threshold) -> StageResult
      - verify_batch(samples, threshold) -> List[StageResult]

    异常结构：
      - RuntimeError: LLM 调用失败（内部捕获，返回失败 StageResult）
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model: str = "gpt-4.1-mini",
        default_threshold: float = 0.7,
    ):
        """
        初始化文本自洽校验器。

        参数:
            llm_client: LLM 客户端
            model: 默认模型名称
            default_threshold: 默认通过阈值
        """
        self._llm = llm_client or LLMClient(model=model)
        self._model = model
        self._default_threshold = default_threshold

    def verify(
        self,
        sample: VLMSample,
        threshold: Optional[float] = None,
    ) -> StageResult:
        """
        对单个 VLMSample 执行文本自洽校验。

        校验维度：
          1. 问题与答案的语义一致性
          2. 图像提示词与场景描述的匹配度
          3. 语义陈述与问答对的逻辑一致性

        参数:
            sample: 待校验的候选样本
            threshold: 通过阈值（覆盖默认值）

        返回:
            StageResult 校验结果
        """
        use_threshold = threshold or self._default_threshold

        system_prompt = (
            "你是一个数据质量审核员。你需要判断以下视觉问答样本的文本部分"
            "是否具备内部一致性。\n\n"
            "请从以下三个维度评估：\n"
            "1. 问题与答案是否语义一致（答案是否合理回答了问题）\n"
            "2. 图像提示词是否能生成与问答相关的图像\n"
            "3. 语义陈述是否与问答对逻辑一致\n\n"
            "请以 JSON 格式返回：\n"
            '{"score": 0.0-1.0, "passed": true/false, "reason": "理由", '
            '"dimensions": {"qa_consistency": 0.0-1.0, "prompt_relevance": 0.0-1.0, '
            '"statement_logic": 0.0-1.0}}'
        )

        user_prompt = (
            f"问题：{sample.question}\n"
            f"答案：{sample.answer}\n"
            f"图像提示词：{sample.image_prompt}\n"
            f"语义陈述：{sample.statement}\n\n"
            f"通过阈值：{use_threshold}"
        )

        try:
            response = self._llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self._model,
                temperature=0.2,
            )

            score = float(response.get("score", 0.0))
            passed = response.get("passed", score >= use_threshold)
            reason = response.get("reason", "")

            return StageResult(
                stage="consistency",
                passed=passed,
                score=score,
                reason=reason,
            )

        except Exception as e:
            logger.error("文本自洽校验失败: %s", e)
            return StageResult(
                stage="consistency",
                passed=False,
                score=0.0,
                reason=f"LLM 调用失败: {e}",
            )

    def verify_batch(
        self,
        samples: List[VLMSample],
        threshold: Optional[float] = None,
    ) -> List[StageResult]:
        """
        批量文本自洽校验。

        参数:
            samples: 样本列表
            threshold: 通过阈值

        返回:
            StageResult 列表
        """
        results = []
        for i, sample in enumerate(samples):
            logger.info("文本自洽校验进度: %d/%d", i + 1, len(samples))
            result = self.verify(sample, threshold)
            results.append(result)
        return results
