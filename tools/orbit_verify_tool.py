"""
ORBIT 级联验证工具 — Hermes 工具层封装。

将 CascadeOrchestrator 的能力封装为 Hermes Agent 可调用的工具函数。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.cascade_orchestrator import CascadeOrchestrator, VerificationResult
from core.rule_verifier import RuleVerifier
from core.semantic_verifier import SemanticVerifier
from core.safety_verifier import SafetyVerifier
from core.seed_engine import Seed
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具 handler
# ---------------------------------------------------------------------------

def _build_orchestrator(params: Dict[str, Any]) -> CascadeOrchestrator:
    """根据参数构建级联编排器。"""
    model_semantic = params.get("model_semantic", "gpt-4.1-mini")
    model_safety = params.get("model_safety", "gpt-4.1-nano")

    llm_semantic = LLMClient(model=model_semantic)
    llm_safety = LLMClient(model=model_safety)

    return CascadeOrchestrator(
        rule_verifier=RuleVerifier(),
        semantic_verifier=SemanticVerifier(llm_client=llm_semantic, model=model_semantic),
        safety_verifier=SafetyVerifier(llm_client=llm_safety, model=model_safety),
    )


def handle_orbit_verify(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理级联验证请求。

    参数 (params):
        variant (str): 待验证的话术变体
        seed (dict): 对应的种子对象
        model_semantic (str, 可选): 语义验证模型
        model_safety (str, 可选): 安全验证模型

    返回:
        {
            "variant": str,
            "overall_passed": bool,
            "confidence_score": float,
            "rule_check": {...},
            "semantic_check": {...},
            "safety_check": {...},
        }
    """
    try:
        variant = params.get("variant", "")
        seed_data = params.get("seed", {})
        seed = Seed.from_dict(seed_data)

        orchestrator = _build_orchestrator(params)
        result = orchestrator.verify(variant, seed)

        return result.to_dict()
    except Exception as e:
        logger.error("验证失败: %s", e)
        return {"error": str(e)}


def handle_orbit_batch_verify(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理批量级联验证请求。

    参数 (params):
        variants (list): 变体列表
        seed (dict): 对应的种子对象
        model_semantic (str, 可选): 语义验证模型
        model_safety (str, 可选): 安全验证模型

    返回:
        {
            "results": [...],
            "total": int,
            "passed": int,
            "failed": int,
            "pass_rate": float,
        }
    """
    try:
        variants = params.get("variants", [])
        seed_data = params.get("seed", {})
        seed = Seed.from_dict(seed_data)

        orchestrator = _build_orchestrator(params)
        results = orchestrator.verify_batch(variants, seed)

        output = [r.to_dict() for r in results]
        passed = sum(1 for r in results if r.overall_passed)
        total = len(results)

        return {
            "results": output,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 3) if total > 0 else 0.0,
        }
    except Exception as e:
        logger.error("批量验证失败: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Hermes ToolRegistry 集成
# ---------------------------------------------------------------------------

ORBIT_VERIFY_TOOL_SCHEMA = {
    "name": "orbit_verify",
    "description": "对话术变体执行三层级联验证（规则→语义→安全）",
    "parameters": {
        "type": "object",
        "properties": {
            "variant": {
                "type": "string",
                "description": "待验证的话术变体",
            },
            "seed": {
                "type": "object",
                "description": "对应的种子对象",
            },
            "model_semantic": {
                "type": "string",
                "description": "语义验证模型名称",
            },
            "model_safety": {
                "type": "string",
                "description": "安全验证模型名称",
            },
        },
        "required": ["variant", "seed"],
    },
}

try:
    from tool_registry import ToolRegistry
    ToolRegistry.register(
        name="orbit_verify",
        handler=handle_orbit_verify,
        schema=ORBIT_VERIFY_TOOL_SCHEMA,
    )
    ToolRegistry.register(
        name="orbit_batch_verify",
        handler=handle_orbit_batch_verify,
        schema={
            "name": "orbit_batch_verify",
            "description": "对变体列表执行批量级联验证",
            "parameters": {
                "type": "object",
                "properties": {
                    "variants": {"type": "array", "items": {"type": "string"}},
                    "seed": {"type": "object"},
                    "model_semantic": {"type": "string"},
                    "model_safety": {"type": "string"},
                },
                "required": ["variants", "seed"],
            },
        },
    )
    logger.info("已注册 orbit_verify / orbit_batch_verify 工具")
except ImportError:
    logger.debug("ToolRegistry 不可用 — 跳过工具注册")
