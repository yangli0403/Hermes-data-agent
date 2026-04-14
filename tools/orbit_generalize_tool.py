"""
ORBIT 多维度泛化工具 — Hermes 工具层封装。

将 GeneralizationEngine 的能力封装为 Hermes Agent 可调用的工具函数。
"""

from __future__ import annotations

import json
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
            "variants": [...],              # 变体列表
            "generation_strategies": [...], # 生成策略
            "dimensions_used": [...],       # 使用的维度
            "count": int,                   # 变体数量
        }
    """
    raise NotImplementedError("将在第4阶段实现")


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
            "results": [...],       # GeneralizationResult 列表
            "total_variants": int,  # 总变体数量
            "total_seeds": int,     # 处理的种子数量
        }
    """
    raise NotImplementedError("将在第4阶段实现")


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
