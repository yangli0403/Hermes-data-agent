"""
ORBIT 种子生成工具 — Hermes 工具层封装。

将 SeedEngine 的能力封装为 Hermes Agent 可调用的工具函数。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from core.seed_engine import SeedEngine, Seed
from core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具 handler
# ---------------------------------------------------------------------------

def handle_orbit_seed_generate(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理种子生成请求。

    参数 (params):
        config_path (str): 功能树配置文件路径（YAML/JSON）
        excel_path (str, 可选): Excel 文件路径（与 config_path 二选一）
        max_seeds (int, 可选): 最大种子数量，默认 1000
        limit (int, 可选): 限制返回的种子数量

    返回:
        {
            "seeds": [...],
            "total_count": int,
            "source_type": str,
        }
    """
    try:
        engine = SeedEngine()
        config_path = params.get("config_path")
        excel_path = params.get("excel_path")
        max_seeds = params.get("max_seeds", 1000)
        limit = params.get("limit")

        if config_path:
            seeds = engine.generate_from_config(config_path, max_seeds=max_seeds)
            source_type = "config"
        elif excel_path:
            seeds = engine.extract_from_excel(excel_path)
            source_type = "excel"
        else:
            return {"error": "必须提供 config_path 或 excel_path 参数"}

        if limit and limit > 0:
            seeds = seeds[:limit]

        return {
            "seeds": [s.to_dict() for s in seeds],
            "total_count": len(seeds),
            "source_type": source_type,
        }
    except Exception as e:
        logger.error("种子生成失败: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Hermes ToolRegistry 集成
# ---------------------------------------------------------------------------

ORBIT_SEED_TOOL_SCHEMA = {
    "name": "orbit_seed_generate",
    "description": "从功能树配置或 Excel 文件中系统化生成 ORBIT 功能种子",
    "parameters": {
        "type": "object",
        "properties": {
            "config_path": {
                "type": "string",
                "description": "功能树配置文件路径（YAML/JSON 格式）",
            },
            "excel_path": {
                "type": "string",
                "description": "Excel 文件路径（与 config_path 二选一）",
            },
            "max_seeds": {
                "type": "integer",
                "description": "最大种子数量（防止组合爆炸），默认 1000",
                "default": 1000,
            },
            "limit": {
                "type": "integer",
                "description": "限制返回的种子数量",
            },
        },
        "required": [],
    },
}

try:
    from tool_registry import ToolRegistry
    ToolRegistry.register(
        name="orbit_seed_generate",
        handler=handle_orbit_seed_generate,
        schema=ORBIT_SEED_TOOL_SCHEMA,
    )
    logger.info("已注册 orbit_seed_generate 工具")
except ImportError:
    logger.debug("ToolRegistry 不可用 — 跳过工具注册")
