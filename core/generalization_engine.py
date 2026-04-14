"""
多维度泛化引擎 — 对种子沿多个维度生成话术变体。

泛化维度包括：
  1. colloquial — 口语化程度变换
  2. sentence_pattern — 句式变化（祈使句、疑问句、陈述句等）
  3. param_variation — 参数变化（保持语义不变）
  4. simplification — 简化与省略
  5. driving_scenario — 驾驶场景适配
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.seed_engine import Seed
from core.llm_client import LLMClient
from core.provenance_tracker import ProvenanceTracker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class GeneralizationResult:
    """泛化结果 — 包含种子和生成的变体列表。"""

    seed: Seed
    variants: List[str] = field(default_factory=list)
    generation_strategies: List[str] = field(default_factory=list)
    dimensions_used: List[str] = field(default_factory=list)
    llm_model: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "seed": self.seed.to_dict(),
            "variants": self.variants,
            "generation_strategies": self.generation_strategies,
            "dimensions_used": self.dimensions_used,
            "llm_model": self.llm_model,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# 维度定义
# ---------------------------------------------------------------------------

DIMENSION_PROMPTS: Dict[str, str] = {
    "colloquial": (
        "口语化变换：将标准话术转换为不同口语化程度的表达。"
        "从正式到非常口语，包括省略词、语气词、缩略语等。"
    ),
    "sentence_pattern": (
        "句式变化：将标准话术转换为不同句式。"
        "包括祈使句、疑问句、陈述句、感叹句等。"
    ),
    "param_variation": (
        "参数变化：保持核心语义不变，变换参数的表达方式。"
        "例如位置描述、时间描述、数量描述的不同说法。"
    ),
    "simplification": (
        "简化与省略：在保持语义可理解的前提下，省略部分信息。"
        "模拟用户在驾驶场景中的简短表达习惯。"
    ),
    "driving_scenario": (
        "驾驶场景适配：将标准话术适配到具体的驾驶场景中。"
        "例如高速行驶、城市拥堵、停车等不同场景下的表达。"
    ),
}

ALL_DIMENSIONS = list(DIMENSION_PROMPTS.keys())


# ---------------------------------------------------------------------------
# 泛化引擎
# ---------------------------------------------------------------------------

class GeneralizationEngine:
    """
    多维度泛化引擎。

    公共接口：
      - generalize(seed, num_variants, dimensions) -> GeneralizationResult
      - generalize_batch(seeds, num_variants, dimensions) -> List[GeneralizationResult]
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        provenance_tracker: Optional[ProvenanceTracker] = None,
        model: str = "gpt-4.1-mini",
    ):
        self._llm = llm_client or LLMClient(model=model)
        self._tracker = provenance_tracker
        self._model = model

    def generalize(
        self,
        seed: Seed,
        num_variants: int = 5,
        dimensions: Optional[List[str]] = None,
    ) -> GeneralizationResult:
        """
        对单个种子执行多维度泛化。

        参数:
            seed: 功能种子
            num_variants: 目标变体数量
            dimensions: 启用的维度列表。None 表示使用全部维度。

        返回:
            泛化结果

        异常:
            ValueError: 无效的维度名称
        """
        dims = dimensions or ALL_DIMENSIONS
        self._validate_dimensions(dims)

        messages = self._build_prompt(seed, num_variants, dims)

        try:
            response = self._llm.chat(messages, model=self._model, temperature=0.8)
            variants = self._parse_variants(response)
        except Exception as e:
            logger.error("泛化失败 (seed=%s): %s", seed.seed_id, e)
            variants = []

        # 去重并过滤空值
        seen = set()
        unique_variants = []
        for v in variants:
            v_clean = v.strip()
            if v_clean and v_clean not in seen and v_clean != seed.standard_utterance:
                seen.add(v_clean)
                unique_variants.append(v_clean)

        # 为每个变体标注生成策略
        strategies = [f"multi_dim:{','.join(dims)}"] * len(unique_variants)

        result = GeneralizationResult(
            seed=seed,
            variants=unique_variants[:num_variants],
            generation_strategies=strategies[:num_variants],
            dimensions_used=dims,
            llm_model=self._model,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # 记录到追踪器
        if self._tracker:
            self._tracker.record_generalization(
                seed=seed,
                variants=result.variants,
                metadata={
                    "dimensions": dims,
                    "model": self._model,
                    "num_requested": num_variants,
                    "num_generated": len(result.variants),
                },
            )

        logger.info(
            "泛化完成: seed=%s, 请求=%d, 生成=%d",
            seed.seed_id, num_variants, len(result.variants),
        )
        return result

    def generalize_batch(
        self,
        seeds: List[Seed],
        num_variants: int = 5,
        dimensions: Optional[List[str]] = None,
    ) -> List[GeneralizationResult]:
        """
        对种子列表执行批量泛化。

        参数:
            seeds: 种子列表
            num_variants: 每个种子的目标变体数量
            dimensions: 启用的维度列表

        返回:
            泛化结果列表
        """
        results = []
        for i, seed in enumerate(seeds):
            logger.info("批量泛化进度: %d/%d (seed=%s)", i + 1, len(seeds), seed.seed_id)
            result = self.generalize(seed, num_variants, dimensions)
            results.append(result)
        return results

    # ---- 内部方法 --------------------------------------------------------

    def _build_prompt(
        self,
        seed: Seed,
        num_variants: int,
        dimensions: List[str],
    ) -> List[Dict[str, str]]:
        """构建多维度泛化 Prompt。"""
        dim_descriptions = "\n".join(
            f"  - {DIMENSION_PROMPTS[d]}" for d in dimensions
        )

        param_info = ""
        if seed.params:
            param_info = f"\n参数信息: {seed.params}\n注意：生成的变体中必须保留关键参数值。"

        system_prompt = (
            "你是一个专业的车载语音助手数据合成专家。你的任务是对给定的标准话术"
            "进行多维度泛化，生成多样化的自然语言变体。\n\n"
            "泛化维度：\n"
            f"{dim_descriptions}\n\n"
            "要求：\n"
            "1. 每个变体必须与标准话术表达相同的意图\n"
            "2. 变体应覆盖多个不同的泛化维度\n"
            "3. 变体要像真实用户在驾驶场景中会说的话\n"
            "4. 变体长度控制在 2-50 个字符之间\n"
            "5. 不要生成与标准话术完全相同的变体\n"
            f"6. 请生成恰好 {num_variants} 个不同的变体\n\n"
            "输出格式：每行一个变体，不要编号，不要引号，不要其他标记。"
        )

        user_prompt = (
            f"标准话术: {seed.standard_utterance}\n"
            f"所属领域: {seed.domain}\n"
            f"功能: {seed.function}"
            f"{param_info}\n\n"
            f"请生成 {num_variants} 个泛化变体："
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_variants(self, response: str) -> List[str]:
        """从 LLM 响应中解析变体列表。"""
        lines = response.strip().split("\n")
        variants = []
        for line in lines:
            # 去除编号前缀（如 "1. ", "1) ", "- " 等）
            cleaned = re.sub(r"^\s*[\d]+[.)\-、]\s*", "", line)
            # 去除引号
            cleaned = cleaned.strip().strip('"').strip("'").strip(""").strip(""")
            if cleaned:
                variants.append(cleaned)
        return variants

    def _validate_dimensions(self, dimensions: List[str]) -> None:
        """验证维度名称是否有效。"""
        invalid = [d for d in dimensions if d not in DIMENSION_PROMPTS]
        if invalid:
            valid = ", ".join(DIMENSION_PROMPTS.keys())
            raise ValueError(
                f"无效的泛化维度: {', '.join(invalid)}。有效维度: {valid}"
            )
