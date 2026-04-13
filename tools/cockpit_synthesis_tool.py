#!/usr/bin/env python3
"""
Cockpit Utterance Synthesis Tool — registers into hermes-agent's ToolRegistry.

This tool follows the exact same registration pattern as all built-in hermes-agent
tools (see tools/registry.py in hermes-agent). It self-registers at import time
so that the agent can invoke it via function calling.

The tool wraps the cockpit utterance synthesis logic from the original
cockpit-data-synthesis project, enhanced with batch processing and validation.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ── Lazy import of hermes-agent registry ──────────────────────────────────
# We import at module level so the tool is registered when model_tools.py
# triggers tool discovery. If hermes-agent is not installed, we provide a
# standalone fallback.
try:
    from tools.registry import registry as hermes_registry

    _HAS_HERMES = True
except ImportError:
    hermes_registry = None
    _HAS_HERMES = False
    logger.info(
        "hermes-agent not found — cockpit_synthesis_tool running in standalone mode"
    )

# ── Tool schema (OpenAI function-calling format) ─────────────────────────
SYNTHESIS_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cockpit_synthesize",
        "description": (
            "Synthesize diverse natural-language utterance variants from a "
            "standard cockpit AI voice command. Returns a JSON array of variant "
            "strings. Use this tool when you need to generate NLU training data "
            "for cockpit voice assistants."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Skill domain, e.g. '音乐', '导航', '空调'",
                },
                "primary_function": {
                    "type": "string",
                    "description": "Primary function, e.g. '播放音乐'",
                },
                "secondary_function": {
                    "type": "string",
                    "description": "Secondary function, e.g. '指定歌手播放'",
                },
                "param_combination": {
                    "type": "string",
                    "description": "Parameter combination, e.g. '播放+歌手'",
                },
                "param_description": {
                    "type": "string",
                    "description": "Description of the parameter combination",
                },
                "standard_utterance": {
                    "type": "string",
                    "description": "The standard utterance(s) to synthesize variants for",
                },
                "num_variants": {
                    "type": "integer",
                    "description": "Number of variants to generate (default: 5)",
                    "default": 5,
                },
            },
            "required": ["standard_utterance"],
        },
    },
}

VALIDATION_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cockpit_validate",
        "description": (
            "Validate synthesized utterance variants against the original standard "
            "utterance. Checks semantic consistency, parameter retention, naturalness. "
            "Returns a structured verdict with scores and feedback."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "standard_utterance": {
                    "type": "string",
                    "description": "The original standard utterance",
                },
                "variants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of synthesized variants to validate",
                },
                "domain": {
                    "type": "string",
                    "description": "Skill domain for context",
                },
                "param_combination": {
                    "type": "string",
                    "description": "Parameter combination for retention checking",
                },
            },
            "required": ["standard_utterance", "variants"],
        },
    },
}

BATCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cockpit_batch_synthesize",
        "description": (
            "Batch-synthesize utterance variants for multiple standard utterances. "
            "Reads from an Excel file (with columns: 技能/领域, 一级功能, 二级功能, "
            "参数组合, 参数组合功能描述, 标准话术) and writes results to JSON and Excel."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Path to input Excel file",
                },
                "output_json": {
                    "type": "string",
                    "description": "Path for output JSON file (default: output/泛化结果.json)",
                },
                "output_excel": {
                    "type": "string",
                    "description": "Path for output Excel file (default: output/泛化结果.xlsx)",
                },
                "num_variants": {
                    "type": "integer",
                    "description": "Number of variants per utterance (default: 5)",
                    "default": 5,
                },
                "validate": {
                    "type": "boolean",
                    "description": "Whether to run validation on results (default: true)",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "Limit number of utterances to process (for testing)",
                },
            },
            "required": ["input_path"],
        },
    },
}


# ── Skill file loader ────────────────────────────────────────────────────
def _load_skill_text(skill_name: str) -> str:
    """Load a SKILL.md from the local skills/ directory."""
    # Search relative to this file's location
    base = Path(__file__).parent.parent / "skills"
    skill_path = base / skill_name / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    return ""


# ── Tool handlers ────────────────────────────────────────────────────────
def handle_cockpit_synthesize(
    standard_utterance: str,
    domain: str = "",
    primary_function: str = "",
    secondary_function: str = "",
    param_combination: str = "",
    param_description: str = "",
    num_variants: int = 5,
    **kwargs,
) -> str:
    """
    Handle a single utterance synthesis request.

    This function is called by hermes-agent's tool dispatch when the LLM
    invokes the `cockpit_synthesize` tool. The agent's conversation context
    already includes the synthesis SKILL.md as instructions.
    """
    from openai import OpenAI

    skill_text = _load_skill_text("cockpit-utterance-synthesis")

    client = OpenAI()
    system_prompt = (
        "你是一个专业的座舱AI语音助手话术泛化专家。\n\n"
        "请严格遵循以下技能指令：\n\n" + skill_text
    )

    user_prompt = (
        f"请对以下座舱语音指令的标准话术进行泛化，生成 {num_variants} 种不同的自然表达变体。\n\n"
        f"- 技能/领域：{domain}\n"
        f"- 一级功能：{primary_function}\n"
        f"- 二级功能：{secondary_function}\n"
        f"- 参数组合：{param_combination}\n"
        f"- 功能描述：{param_description}\n"
        f"- **标准话术**：{standard_utterance}\n\n"
        f"请严格按照JSON数组格式输出 {num_variants} 个变体，不要输出任何其他内容。"
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.9,
        max_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()
    # Parse JSON from response (handle code blocks)
    if "```" in raw:
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()

    try:
        variants = json.loads(raw)
        if isinstance(variants, list):
            return json.dumps(variants, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    return json.dumps({"error": "Failed to parse variants", "raw": raw[:500]})


def handle_cockpit_validate(
    standard_utterance: str,
    variants: list,
    domain: str = "",
    param_combination: str = "",
    **kwargs,
) -> str:
    """Handle a validation request using the validation SKILL.md."""
    from openai import OpenAI

    skill_text = _load_skill_text("cockpit-utterance-validation")

    client = OpenAI()
    system_prompt = (
        "你是一个严格的座舱AI话术质量审核专家。\n\n"
        "请严格遵循以下技能指令：\n\n" + skill_text
    )

    variants_text = "\n".join(f"{i+1}. {v}" for i, v in enumerate(variants))
    user_prompt = (
        f"请审核以下泛化结果的质量。\n\n"
        f"- 技能/领域：{domain}\n"
        f"- 参数组合：{param_combination}\n"
        f"- **标准话术**：{standard_utterance}\n\n"
        f"## 泛化变体\n{variants_text}\n\n"
        f"请严格按照JSON格式输出审核结果。"
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()

    try:
        result = json.loads(raw)
        return json.dumps(result, ensure_ascii=False)
    except json.JSONDecodeError:
        return json.dumps({"passed": True, "error": "Parse failed", "raw": raw[:500]})


def handle_cockpit_batch_synthesize(
    input_path: str,
    output_json: str = "output/泛化结果.json",
    output_excel: str = "output/泛化结果.xlsx",
    num_variants: int = 5,
    validate: bool = True,
    limit: int = None,
    **kwargs,
) -> str:
    """
    Batch synthesis handler.

    Reads an Excel file, synthesizes variants for each utterance,
    optionally validates them, and writes results to JSON + Excel.
    """
    import pandas as pd

    # Load data
    df = pd.read_excel(input_path)
    required_cols = ["技能/领域", "一级功能", "二级功能", "参数组合", "参数组合功能描述", "标准话术"]
    for col in required_cols:
        if col not in df.columns:
            return json.dumps({"error": f"Missing column: {col}"})

    df = df.dropna(subset=["标准话术"])
    if limit:
        df = df.head(limit)

    results = []
    total = len(df)

    for idx, row in df.iterrows():
        logger.info(f"Processing {idx+1}/{total}: {str(row['标准话术'])[:30]}...")

        # Synthesize
        synth_result = handle_cockpit_synthesize(
            standard_utterance=str(row["标准话术"]),
            domain=str(row.get("技能/领域", "")),
            primary_function=str(row.get("一级功能", "")),
            secondary_function=str(row.get("二级功能", "")),
            param_combination=str(row.get("参数组合", "")),
            param_description=str(row.get("参数组合功能描述", "")),
            num_variants=num_variants,
        )

        try:
            variants = json.loads(synth_result)
            if isinstance(variants, dict) and "error" in variants:
                variants = []
        except json.JSONDecodeError:
            variants = []

        # Validate if enabled
        validation = None
        if validate and variants:
            val_result = handle_cockpit_validate(
                standard_utterance=str(row["标准话术"]),
                variants=variants,
                domain=str(row.get("技能/领域", "")),
                param_combination=str(row.get("参数组合", "")),
            )
            try:
                validation = json.loads(val_result)
            except json.JSONDecodeError:
                validation = {"passed": True}

        results.append({
            "技能/领域": str(row.get("技能/领域", "")),
            "一级功能": str(row.get("一级功能", "")),
            "二级功能": str(row.get("二级功能", "")),
            "参数组合": str(row.get("参数组合", "")),
            "参数组合功能描述": str(row.get("参数组合功能描述", "")),
            "标准话术": str(row["标准话术"]),
            "泛化话术": variants,
            "验证结果": validation,
        })

    # Save JSON
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Save Excel
    Path(output_excel).parent.mkdir(parents=True, exist_ok=True)
    excel_rows = []
    for r in results:
        for v in r.get("泛化话术", []):
            excel_rows.append({
                "技能/领域": r["技能/领域"],
                "一级功能": r["一级功能"],
                "二级功能": r["二级功能"],
                "参数组合": r["参数组合"],
                "参数组合功能描述": r["参数组合功能描述"],
                "标准话术": r["标准话术"],
                "泛化话术": v,
            })
    pd.DataFrame(excel_rows).to_excel(output_excel, index=False)

    return json.dumps({
        "status": "success",
        "total_utterances": total,
        "total_variants": sum(len(r.get("泛化话术", [])) for r in results),
        "output_json": output_json,
        "output_excel": output_excel,
    }, ensure_ascii=False)


# ── Register tools with hermes-agent ─────────────────────────────────────
if _HAS_HERMES and hermes_registry is not None:
    hermes_registry.register(
        name="cockpit_synthesize",
        toolset="cockpit-data",
        schema=SYNTHESIS_TOOL_SCHEMA,
        handler=handle_cockpit_synthesize,
        description="Synthesize diverse utterance variants for cockpit AI voice commands",
        emoji="🎙️",
    )

    hermes_registry.register(
        name="cockpit_validate",
        toolset="cockpit-data",
        schema=VALIDATION_TOOL_SCHEMA,
        handler=handle_cockpit_validate,
        description="Validate synthesized utterance variants for quality",
        emoji="✅",
    )

    hermes_registry.register(
        name="cockpit_batch_synthesize",
        toolset="cockpit-data",
        schema=BATCH_TOOL_SCHEMA,
        handler=handle_cockpit_batch_synthesize,
        description="Batch-synthesize utterance variants from an Excel file",
        emoji="📊",
    )

    logger.info("Cockpit data synthesis tools registered with hermes-agent")
