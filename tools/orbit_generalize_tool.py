"""
ORBIT 多维度泛化工具 — Hermes 工具层封装。

将 GeneralizationEngine 的能力封装为 Hermes Agent 可调用的工具函数。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.generalization_engine import GeneralizationEngine, GeneralizationResult
from core.seed_engine import Seed
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具 handler
# ---------------------------------------------------------------------------

def handle_orbit_generalize(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理多维度泛化请求。

    参数 (params):
        seed (dict): 种子对象（包含 domain, function, standard_utterance 等）
        num_variants (int, 可选): 目标变体数量，默认 5
        dimensions (list, 可选): 启用的维度列表
        model (str, 可选): LLM 模型名称

    返回:
        {
            "variants": [...],
            "generation_strategies": [...],
            "dimensions_used": [...],
            "count": int,
        }
    """
    try:
        seed_data = params.get("seed", {})
        seed = Seed.from_dict(seed_data)
        num_variants = params.get("num_variants", 5)
        dimensions = params.get("dimensions")
        model = params.get("model", "gpt-4.1-mini")

        llm = LLMClient(model=model)
        engine = GeneralizationEngine(llm_client=llm, model=model)
        result = engine.generalize(seed, num_variants=num_variants, dimensions=dimensions)

        return {
            "variants": result.variants,
            "generation_strategies": result.generation_strategies,
            "dimensions_used": result.dimensions_used,
            "count": len(result.variants),
        }
    except Exception as e:
        logger.error("泛化失败: %s", e)
        return {"error": str(e)}


def handle_orbit_batch_generalize(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理批量泛化请求。

    参数 (params):
        seeds (list): 种子对象列表
        num_variants (int, 可选): 每个种子的目标变体数量
        dimensions (list, 可选): 启用的维度列表
        model (str, 可选): LLM 模型名称

    返回:
        {
            "results": [...],
            "total_variants": int,
            "total_seeds": int,
        }
    """
    try:
        seeds_data = params.get("seeds", [])
        seeds = [Seed.from_dict(s) for s in seeds_data]
        num_variants = params.get("num_variants", 5)
        dimensions = params.get("dimensions")
        model = params.get("model", "gpt-4.1-mini")

        llm = LLMClient(model=model)
        engine = GeneralizationEngine(llm_client=llm, model=model)
        results = engine.generalize_batch(seeds, num_variants=num_variants, dimensions=dimensions)

        output = []
        total_variants = 0
        for r in results:
            output.append({
                "seed_id": r.seed.seed_id,
                "variants": r.variants,
                "num_generated": len(r.variants),
            })
            total_variants += len(r.variants)

        return {
            "results": output,
            "total_variants": total_variants,
            "total_seeds": len(seeds),
        }
    except Exception as e:
        logger.error("批量泛化失败: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Hermes ToolRegistry 集成
# ---------------------------------------------------------------------------

ORBIT_GENERALIZE_TOOL_SCHEMA = {
    "name": "orbit_generalize",
    "description": "对种子执行多维度泛化，生成话术变体",
    "parameters": {
        "type": "object",
        "properties": {
            "seed": {
                "type": "object",
                "description": "种子对象",
            },
            "num_variants": {
                "type": "integer",
                "description": "目标变体数量，默认 5",
                "default": 5,
            },
            "dimensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "启用的维度列表",
            },
            "model": {
                "type": "string",
                "description": "LLM 模型名称",
            },
        },
        "required": ["seed"],
    },
}

try:
    from tool_registry import ToolRegistry
    ToolRegistry.register(
        name="orbit_generalize",
        handler=handle_orbit_generalize,
        schema=ORBIT_GENERALIZE_TOOL_SCHEMA,
    )
    ToolRegistry.register(
        name="orbit_batch_generalize",
        handler=handle_orbit_batch_generalize,
        schema={
            "name": "orbit_batch_generalize",
            "description": "对种子列表执行批量多维度泛化",
            "parameters": {
                "type": "object",
                "properties": {
                    "seeds": {"type": "array", "description": "种子对象列表"},
                    "num_variants": {"type": "integer", "default": 5},
                    "dimensions": {"type": "array", "items": {"type": "string"}},
                    "model": {"type": "string"},
                },
                "required": ["seeds"],
            },
        },
    )
    logger.info("已注册 orbit_generalize / orbit_batch_generalize 工具")
except ImportError:
    logger.debug("ToolRegistry 不可用 — 跳过工具注册")
