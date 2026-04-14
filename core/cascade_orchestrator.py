"""
级联验证编排器 — 编排三层级联验证流水线。

采用"短路"策略：某层验证失败则跳过后续层（节省 API 成本）。
同时记录每层验证结果到验证链中，确保完整的可追溯性。

流水线：规则验证 → 语义验证 → 安全验证
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.seed_engine import Seed
from core.rule_verifier import RuleVerifier, StageResult
from core.semantic_verifier import SemanticVerifier
from core.safety_verifier import SafetyVerifier
from core.provenance_tracker import ProvenanceTracker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """完整的级联验证结果。"""

    variant: str
    rule_check: StageResult
    semantic_check: Optional[StageResult] = None
    safety_check: Optional[StageResult] = None
    overall_passed: bool = False
    confidence_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        result = {
            "variant": self.variant,
            "rule_check": self.rule_check.to_dict(),
            "overall_passed": self.overall_passed,
            "confidence_score": self.confidence_score,
        }
        if self.semantic_check:
            result["semantic_check"] = self.semantic_check.to_dict()
        else:
            result["semantic_check"] = {"stage": "semantic", "passed": False, "score": 0.0, "reason": "skipped"}
        if self.safety_check:
            result["safety_check"] = self.safety_check.to_dict()
        else:
            result["safety_check"] = {"stage": "safety", "passed": False, "score": 0.0, "reason": "skipped"}
        return result


# ---------------------------------------------------------------------------
# 级联编排器
# ---------------------------------------------------------------------------

class CascadeOrchestrator:
    """
    级联验证编排器。

    公共接口：
      - verify(variant, seed) -> VerificationResult
      - verify_batch(variants, seed) -> List[VerificationResult]
    """

    def __init__(
        self,
        rule_verifier: Optional[RuleVerifier] = None,
        semantic_verifier: Optional[SemanticVerifier] = None,
        safety_verifier: Optional[SafetyVerifier] = None,
        provenance_tracker: Optional[ProvenanceTracker] = None,
    ):
        self._rule = rule_verifier or RuleVerifier()
        self._semantic = semantic_verifier or SemanticVerifier()
        self._safety = safety_verifier or SafetyVerifier()
        self._tracker = provenance_tracker

    def verify(self, variant: str, seed: Seed) -> VerificationResult:
        """
        对单个变体执行级联验证。

        短路策略：规则验证失败 → 跳过语义和安全验证。
                  语义验证失败 → 跳过安全验证。

        参数:
            variant: 待验证的话术变体
            seed: 对应的种子

        返回:
            完整的级联验证结果
        """
        # 第一层：规则验证（零成本）
        rule_result = self._rule.verify(variant, seed)

        if not rule_result.passed:
            result = VerificationResult(
                variant=variant,
                rule_check=rule_result,
                semantic_check=None,
                safety_check=None,
                overall_passed=False,
                confidence_score=0.0,
            )
            self._record_verification(seed, variant, result)
            logger.debug("规则验证失败: '%s' — %s", variant, rule_result.reason)
            return result

        # 第二层：语义验证（LLM 调用）
        semantic_result = self._semantic.verify(variant, seed)

        if not semantic_result.passed:
            confidence = self._compute_confidence(rule_result, semantic_result, None)
            result = VerificationResult(
                variant=variant,
                rule_check=rule_result,
                semantic_check=semantic_result,
                safety_check=None,
                overall_passed=False,
                confidence_score=confidence,
            )
            self._record_verification(seed, variant, result)
            logger.debug("语义验证失败: '%s' — %s", variant, semantic_result.reason)
            return result

        # 第三层：安全验证（LLM 调用）
        safety_result = self._safety.verify(variant, seed)

        confidence = self._compute_confidence(rule_result, semantic_result, safety_result)
        overall_passed = safety_result.passed

        result = VerificationResult(
            variant=variant,
            rule_check=rule_result,
            semantic_check=semantic_result,
            safety_check=safety_result,
            overall_passed=overall_passed,
            confidence_score=confidence,
        )
        self._record_verification(seed, variant, result)

        if overall_passed:
            logger.debug("验证通过: '%s' (置信度=%.3f)", variant, confidence)
        else:
            logger.debug("安全验证失败: '%s' — %s", variant, safety_result.reason)

        return result

    def verify_batch(
        self, variants: List[str], seed: Seed
    ) -> List[VerificationResult]:
        """
        对变体列表执行批量级联验证。

        参数:
            variants: 变体列表
            seed: 对应的种子

        返回:
            验证结果列表
        """
        results = []
        for i, variant in enumerate(variants):
            logger.info("级联验证进度: %d/%d", i + 1, len(variants))
            result = self.verify(variant, seed)
            results.append(result)
        return results

    # ---- 内部方法 --------------------------------------------------------

    def _compute_confidence(
        self,
        rule_result: StageResult,
        semantic_result: Optional[StageResult],
        safety_result: Optional[StageResult],
    ) -> float:
        """
        汇总三层验证分数为综合置信度。

        计算公式：
          confidence = rule_score * 0.2 + semantic_score * 0.4 + safety_score * 0.4
        """
        rule_score = rule_result.score
        semantic_score = semantic_result.score if semantic_result else 0.0
        safety_score = safety_result.score if safety_result else 0.0

        confidence = rule_score * 0.2 + semantic_score * 0.4 + safety_score * 0.4
        return round(confidence, 3)

    def _record_verification(
        self,
        seed: Seed,
        variant: str,
        result: VerificationResult,
    ) -> None:
        """记录验证结果到追踪器。"""
        if self._tracker:
            self._tracker.record_verification(
                seed=seed,
                variant=variant,
                verification_result=result.to_dict(),
            )
