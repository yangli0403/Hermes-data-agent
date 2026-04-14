"""
规则验证器 — 基于纯 Python 逻辑执行快速规则检查。

这是级联验证的第一层，零 API 成本，用于快速过滤明显不合格的变体。

验证规则包括：
  1. 参数完整性 — 关键参数是否在变体中保留
  2. 长度约束 — 变体长度是否在合理范围内
  3. 车辆约束 — 是否违反车辆功能约束规则
  4. 基础语法 — 是否包含明显的语法错误标记
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from core.seed_engine import Seed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    """单层验证结果。"""

    stage: str          # "rule" | "semantic" | "safety"
    passed: bool
    score: float        # 0.0-1.0
    reason: str         # 通过/失败原因

    def to_dict(self) -> Dict:
        return {
            "stage": self.stage,
            "passed": self.passed,
            "score": self.score,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# 车辆约束规则
# ---------------------------------------------------------------------------

VEHICLE_CONSTRAINTS: List[Dict] = [
    {
        "name": "行驶中禁止视频",
        "pattern": r"(播放视频|看视频|放视频|看电影|播放电影)",
        "condition": "driving",
        "message": "行驶中不允许播放视频内容",
    },
    {
        "name": "空变体",
        "pattern": r"^\s*$",
        "condition": "always",
        "message": "变体内容为空",
    },
]


# ---------------------------------------------------------------------------
# 规则验证器
# ---------------------------------------------------------------------------

class RuleVerifier:
    """
    规则验证器。

    公共接口：
      - verify(variant, seed) -> StageResult
      - verify_batch(variants, seed) -> List[StageResult]
    """

    def __init__(
        self,
        min_length: int = 2,
        max_length: int = 50,
        custom_constraints: Optional[List[Dict]] = None,
    ):
        self._min_length = min_length
        self._max_length = max_length
        self._constraints = (custom_constraints or []) + VEHICLE_CONSTRAINTS

    def verify(self, variant: str, seed: Seed) -> StageResult:
        """
        对单个变体执行规则验证。

        参数:
            variant: 待验证的话术变体
            seed: 对应的种子（用于参数完整性检查）

        返回:
            验证结果
        """
        # 依次检查各规则，任一失败则立即返回
        checks = [
            self._check_empty(variant),
            self._check_length(variant),
            self._check_constraints(variant),
            self._check_params(variant, seed),
        ]

        for failure_reason in checks:
            if failure_reason is not None:
                return StageResult(
                    stage="rule",
                    passed=False,
                    score=0.0,
                    reason=failure_reason,
                )

        return StageResult(
            stage="rule",
            passed=True,
            score=1.0,
            reason="参数完整，长度合规，无约束违规",
        )

    def verify_batch(
        self, variants: List[str], seed: Seed
    ) -> List[StageResult]:
        """
        对变体列表执行批量规则验证。

        参数:
            variants: 变体列表
            seed: 对应的种子

        返回:
            验证结果列表
        """
        return [self.verify(v, seed) for v in variants]

    # ---- 内部方法 --------------------------------------------------------

    def _check_empty(self, variant: str) -> Optional[str]:
        """检查是否为空。"""
        if not variant or not variant.strip():
            return "变体内容为空"
        return None

    def _check_length(self, variant: str) -> Optional[str]:
        """检查长度约束，返回失败原因或 None。"""
        length = len(variant.strip())
        if length < self._min_length:
            return f"变体过短（{length} 字符 < 最小 {self._min_length}）"
        if length > self._max_length:
            return f"变体过长（{length} 字符 > 最大 {self._max_length}）"
        return None

    def _check_params(self, variant: str, seed: Seed) -> Optional[str]:
        """检查参数完整性，返回失败原因或 None。"""
        if not seed.params:
            return None

        # 对于每个关键参数值，检查是否在变体中出现
        missing = []
        for key, value in seed.params.items():
            value_str = str(value)
            if value_str and value_str not in variant:
                missing.append(f"{key}={value_str}")

        if missing:
            return f"缺少关键参数: {', '.join(missing)}"
        return None

    def _check_constraints(self, variant: str) -> Optional[str]:
        """检查车辆约束规则，返回失败原因或 None。"""
        for constraint in self._constraints:
            pattern = constraint.get("pattern", "")
            condition = constraint.get("condition", "always")

            # 跳过空变体检查（已在 _check_empty 中处理）
            if constraint.get("name") == "空变体":
                continue

            if condition == "always" or condition == "driving":
                if re.search(pattern, variant):
                    return f"违反车辆约束[{constraint['name']}]: {constraint['message']}"

        return None
