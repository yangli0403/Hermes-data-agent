"""
ORBIT 种子生成工具 — Hermes 工具层封装。

将 SeedEngine 的能力封装为 Hermes Agent 可调用的工具函数。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

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
            "seeds": [...],         # 种子列表
            "total_count": int,     # 总种子数
            "source_type": str,     # "config" | "excel"
        }
    """
    raise NotImplementedError("将在第4阶段实现")


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
