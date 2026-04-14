"""
安全验证器 — 调用 LLM 检查变体是否存在驾驶安全风险。

这是级联验证的第三层（最严格），检查以下维度：
  1. 驾驶安全 — 变体指令是否可能导致驾驶分心
  2. 法规合规 — 是否符合车载系统法规要求
  3. 隐私保护 — 是否涉及不当的隐私数据访问
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.seed_engine import Seed
from core.rule_verifier import StageResult
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SafetyVerifier:
    """
    安全验证器。

    公共接口：
      - verify(variant, seed) -> StageResult
      - verify_batch(variants, seed) -> List[StageResult]
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model: str = "gpt-4.1-nano",
        threshold: float = 0.8,
    ):
        self._llm = llm_client or LLMClient(model=model)
        self._model = model
        self._threshold = threshold

    def verify(self, variant: str, seed: Seed) -> StageResult:
        """
        对单个变体执行安全验证。

        参数:
            variant: 待验证的话术变体
            seed: 对应的种子

        返回:
            验证结果，包含安全评分
        """
        messages = self._build_safety_prompt(variant, seed)

        try:
            result = self._llm.chat_json(messages, model=self._model, temperature=0.1)
            return self._parse_safety_result(result)
        except Exception as e:
            logger.warning("安全验证 LLM 调用失败: %s — 使用保守评分", e)
            return StageResult(
                stage="safety",
                passed=False,
                score=0.5,
                reason=f"LLM 调用失败: {e}",
            )

    def verify_batch(
        self, variants: List[str], seed: Seed
    ) -> List[StageResult]:
        """
        对变体列表执行批量安全验证。

        参数:
            variants: 变体列表
            seed: 对应的种子

        返回:
            验证结果列表
        """
        return [self.verify(v, seed) for v in variants]

    # ---- 内部方法 --------------------------------------------------------

    def _build_safety_prompt(
        self, variant: str, seed: Seed
    ) -> List[Dict[str, str]]:
        """构建安全验证 Prompt。"""
        system_prompt = (
            "你是一个车载系统安全审核专家。你需要评估一个语音指令变体是否存在安全风险。\n\n"
            "评估维度：\n"
            "1. driving_safety (0.0-1.0): 该指令是否可能导致驾驶分心或危险操作\n"
            "   - 1.0 = 完全安全（如播放音乐、调节空调）\n"
            "   - 0.5 = 需要注意（如复杂的导航设置）\n"
            "   - 0.0 = 危险（如要求观看视频、进行复杂的手动操作）\n"
            "2. regulatory_compliance (0.0-1.0): 是否符合车载系统法规要求\n"
            "3. privacy_safety (0.0-1.0): 是否涉及不当的隐私数据访问\n\n"
            "请以 JSON 格式输出：\n"
            '{"driving_safety": 0.95, "regulatory_compliance": 1.0, '
            '"privacy_safety": 1.0, "overall_score": 0.98, '
            '"risk_level": "low", "reason": "简要说明"}\n\n'
            "risk_level 取值: low / medium / high"
        )

        user_prompt = (
            f"标准话术: {seed.standard_utterance}\n"
            f"所属领域: {seed.domain}\n"
            f"功能: {seed.function}\n"
            f"待评估变体: {variant}\n\n"
            "请评估该变体的安全性："
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_safety_result(self, response: Dict[str, Any]) -> StageResult:
        """解析 LLM 返回的安全验证结果。"""
        score = float(response.get("overall_score", 0.0))
        reason = response.get("reason", "")
        risk_level = response.get("risk_level", "unknown")

        # 如果没有 overall_score，计算三个维度的加权平均
        if "overall_score" not in response:
            ds = float(response.get("driving_safety", 0.0))
            rc = float(response.get("regulatory_compliance", 0.0))
            ps = float(response.get("privacy_safety", 0.0))
            score = ds * 0.5 + rc * 0.3 + ps * 0.2

        passed = score >= self._threshold

        if not reason:
            reason = (
                f"安全分数={score:.2f}, 风险等级={risk_level}"
                + (" (通过)" if passed else f" (低于阈值 {self._threshold})")
            )

        return StageResult(
            stage="safety",
            passed=passed,
            score=round(score, 3),
            reason=reason,
        )
