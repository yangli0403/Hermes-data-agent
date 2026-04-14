"""
语义验证器 — 调用 LLM 判断变体与原始话术的语义一致性和自然度。

这是级联验证的第二层，通过 LLM 评判以下维度：
  1. 语义一致性 — 变体是否与标准话术表达相同的意图
  2. 自然度 — 变体是否像真实用户在驾驶场景中会说的话
  3. NLU 可理解性 — NLU 模型是否能正确理解该变体
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.seed_engine import Seed
from core.rule_verifier import StageResult
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SemanticVerifier:
    """
    语义验证器。

    公共接口：
      - verify(variant, seed) -> StageResult
      - verify_batch(variants, seed) -> List[StageResult]
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model: str = "gpt-4.1-mini",
        threshold: float = 0.7,
    ):
        self._llm = llm_client or LLMClient(model=model)
        self._model = model
        self._threshold = threshold

    def verify(self, variant: str, seed: Seed) -> StageResult:
        """
        对单个变体执行语义验证。

        参数:
            variant: 待验证的话术变体
            seed: 对应的种子

        返回:
            验证结果，包含语义一致性分数
        """
        messages = self._build_verification_prompt(variant, seed)

        try:
            result = self._llm.chat_json(messages, model=self._model, temperature=0.1)
            return self._parse_verification_result(result)
        except Exception as e:
            logger.warning("语义验证 LLM 调用失败: %s — 使用保守评分", e)
            return StageResult(
                stage="semantic",
                passed=False,
                score=0.5,
                reason=f"LLM 调用失败: {e}",
            )

    def verify_batch(
        self, variants: List[str], seed: Seed
    ) -> List[StageResult]:
        """
        对变体列表执行批量语义验证。

        参数:
            variants: 变体列表
            seed: 对应的种子

        返回:
            验证结果列表
        """
        return [self.verify(v, seed) for v in variants]

    # ---- 内部方法 --------------------------------------------------------

    def _build_verification_prompt(
        self, variant: str, seed: Seed
    ) -> List[Dict[str, str]]:
        """构建语义验证 Prompt。"""
        system_prompt = (
            "你是一个专业的车载语音助手 NLU 数据质量评审专家。\n"
            "你需要评估一个话术变体与标准话术之间的语义一致性和自然度。\n\n"
            "评估维度：\n"
            "1. semantic_consistency (0.0-1.0): 变体是否与标准话术表达相同的意图\n"
            "2. naturalness (0.0-1.0): 变体是否像真实用户在驾驶场景中会说的话\n"
            "3. nlu_clarity (0.0-1.0): NLU 模型是否能正确理解该变体\n\n"
            "请以 JSON 格式输出：\n"
            '{"semantic_consistency": 0.9, "naturalness": 0.8, "nlu_clarity": 0.85, '
            '"overall_score": 0.85, "reason": "简要说明"}'
        )

        user_prompt = (
            f"标准话术: {seed.standard_utterance}\n"
            f"所属领域: {seed.domain}\n"
            f"功能: {seed.function}\n"
            f"待评估变体: {variant}\n\n"
            "请评估该变体的语义质量："
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_verification_result(self, response: Dict[str, Any]) -> StageResult:
        """解析 LLM 返回的验证结果。"""
        score = float(response.get("overall_score", 0.0))
        reason = response.get("reason", "")

        # 如果没有 overall_score，计算三个维度的加权平均
        if "overall_score" not in response:
            sc = float(response.get("semantic_consistency", 0.0))
            nat = float(response.get("naturalness", 0.0))
            nlu = float(response.get("nlu_clarity", 0.0))
            score = sc * 0.4 + nat * 0.3 + nlu * 0.3

        passed = score >= self._threshold

        if not reason:
            reason = f"语义分数={score:.2f}" + (" (通过)" if passed else f" (低于阈值 {self._threshold})")

        return StageResult(
            stage="semantic",
            passed=passed,
            score=round(score, 3),
            reason=reason,
        )
