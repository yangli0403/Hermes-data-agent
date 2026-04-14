"""
语义验证器 — 调用 LLM 判断变体与原始话术的语义一致性和自然度。

这是级联验证的第二层，通过 LLM 评判以下维度：
  1. 语义一致性 — 变体是否与标准话术表达相同的意图
  2. 自然度 — 变体是否像真实用户在驾驶场景中会说的话
  3. NLU 可理解性 — NLU 模型是否能正确理解该变体
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

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
        raise NotImplementedError("将在第4阶段实现")

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
        raise NotImplementedError("将在第4阶段实现")

    # ---- 内部方法 --------------------------------------------------------

    def _build_verification_prompt(
        self, variant: str, seed: Seed
    ) -> List[Dict[str, str]]:
        """构建语义验证 Prompt。"""
        raise NotImplementedError

    def _parse_verification_result(self, response: Dict) -> StageResult:
        """解析 LLM 返回的验证结果。"""
        raise NotImplementedError
