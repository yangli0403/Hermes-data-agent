"""
安全验证器 — 调用 LLM 检查变体是否存在驾驶安全风险。

这是级联验证的第三层（最严格），检查以下维度：
  1. 驾驶安全 — 变体指令是否可能导致驾驶分心
  2. 法规合规 — 是否符合车载系统法规要求
  3. 隐私保护 — 是否涉及不当的隐私数据访问
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

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
        raise NotImplementedError("将在第4阶段实现")

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
        raise NotImplementedError("将在第4阶段实现")

    # ---- 内部方法 --------------------------------------------------------

    def _build_safety_prompt(
        self, variant: str, seed: Seed
    ) -> List[Dict[str, str]]:
        """构建安全验证 Prompt。"""
        raise NotImplementedError

    def _parse_safety_result(self, response: Dict) -> StageResult:
        """解析 LLM 返回的安全验证结果。"""
        raise NotImplementedError
