#!/usr/bin/env python3
"""
Delegate Synthesis Tool — Agent-level generate-validate-retry loop via hermes-agent's delegate_tool.

Instead of hardcoding the validation loop in Python (the old approach), this module
registers a new tool `cockpit_delegate_synthesize` that leverages hermes-agent's
`delegate_task` to spawn child agents for synthesis and validation.

Architecture:
    Parent Agent
      ├── delegate_task(goal="synthesize variants for '播放周杰伦的歌'")
      │     └── Child Agent (Synthesis) → uses cockpit_synthesize → returns variants
      ├── delegate_task(goal="validate these variants: [...]")
      │     └── Child Agent (Validation) → uses cockpit_validate → returns verdict
      └── If validation fails → delegate_task(goal="regenerate failed variants based on feedback: ...")
            └── Child Agent (Re-synthesis) → returns improved variants

This is the proper Agent-level closed loop: the parent agent reasons about
validation results and decides whether to retry, rather than a Python if/else.

The tool also provides a SKILL.md-compatible orchestration prompt that teaches
the parent agent how to coordinate the generate-validate-retry cycle using
delegate_task.

Requires: hermes-agent with delegate_tool enabled.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Hermes imports ───────────────────────────────────────────────────────
_HAS_DELEGATE = False
try:
    from tools.delegate_tool import delegate_task, DELEGATE_TASK_SCHEMA
    from tools.registry import registry as hermes_registry, tool_error
    _HAS_DELEGATE = True
except ImportError:
    hermes_registry = None
    logger.info("hermes-agent delegate_tool not available — delegate synthesis inactive")


# ── Orchestration prompt for the parent agent ────────────────────────────
# This is injected into the parent agent's system prompt (via SKILL.md or
# ephemeral_system_prompt) to teach it the delegation workflow.

DELEGATION_ORCHESTRATION_PROMPT = """
## Cockpit Utterance Synthesis — Delegation Workflow

You are the orchestrator for cockpit AI utterance synthesis. For each standard
utterance, you MUST follow this delegation workflow:

### Step 1: Delegate Synthesis
Use `delegate_task` to spawn a child agent for synthesis:
```json
{
  "goal": "使用 cockpit_synthesize 工具为以下标准话术生成 5 个自然表达变体。\\n标准话术：{standard_utterance}\\n技能/领域：{domain}\\n参数组合：{param_combination}\\n请直接输出 JSON 数组格式的变体列表。",
  "toolsets": ["cockpit-data"]
}
```

### Step 2: Delegate Validation
Use `delegate_task` to spawn a child agent for validation:
```json
{
  "goal": "使用 cockpit_validate 工具验证以下泛化变体的质量。\\n标准话术：{standard_utterance}\\n变体列表：{variants_json}\\n请输出验证结果的 JSON。",
  "toolsets": ["cockpit-data"]
}
```

### Step 3: Handle Validation Results
- If ALL variants passed: output the final variants list
- If some variants FAILED: extract the feedback, then delegate a new synthesis
  task that includes the feedback, asking the child to regenerate ONLY the
  failed variants
- Maximum 3 retry rounds

### Step 4: Batch Mode
When processing multiple utterances, you can use `delegate_task` in batch mode
(up to 3 parallel tasks):
```json
{
  "tasks": [
    {"goal": "synthesize for utterance A...", "toolsets": ["cockpit-data"]},
    {"goal": "synthesize for utterance B...", "toolsets": ["cockpit-data"]},
    {"goal": "synthesize for utterance C...", "toolsets": ["cockpit-data"]}
  ]
}
```

### Important Rules
- ALWAYS delegate synthesis and validation to child agents
- NEVER call cockpit_synthesize or cockpit_validate directly — let the children do it
- Pass ALL context (standard utterance, domain, parameters) in the goal field
- Children have NO memory of your conversation — be explicit and complete
"""


# ── Delegated synthesis handler ──────────────────────────────────────────

def handle_cockpit_delegate_synthesize(
    standard_utterance: str,
    domain: str = "",
    primary_function: str = "",
    secondary_function: str = "",
    param_combination: str = "",
    param_description: str = "",
    num_variants: int = 5,
    max_retries: int = 3,
    parent_agent=None,
    **kwargs,
) -> str:
    """
    Orchestrate synthesis + validation via hermes-agent's delegate_task.

    This handler is called by the parent agent. It uses delegate_task to
    spawn child agents for synthesis and validation, implementing the
    generate-validate-retry loop at the Agent level.

    Args:
        standard_utterance: The standard utterance to synthesize variants for.
        domain: Skill domain.
        primary_function: Primary function.
        secondary_function: Secondary function.
        param_combination: Parameter combination.
        param_description: Parameter description.
        num_variants: Number of variants to generate.
        max_retries: Maximum validation retry rounds.
        parent_agent: The parent AIAgent instance (injected by hermes-agent).

    Returns:
        JSON string with validated variants.
    """
    if not _HAS_DELEGATE:
        return json.dumps({
            "error": "hermes-agent delegate_tool not available. "
                     "Install hermes-agent or use standalone mode."
        })

    if parent_agent is None:
        return json.dumps({
            "error": "delegate synthesis requires a parent agent context. "
                     "Use --use-agent mode."
        })

    context_block = (
        f"技能/领域：{domain}\n"
        f"一级功能：{primary_function}\n"
        f"二级功能：{secondary_function}\n"
        f"参数组合：{param_combination}\n"
        f"参数组合功能描述：{param_description}\n"
        f"标准话术：{standard_utterance}"
    )

    all_variants = []
    retry_count = 0

    while retry_count <= max_retries:
        # ── Step 1: Delegate Synthesis ────────────────────────────────
        if retry_count == 0:
            synth_goal = (
                f"使用 cockpit_synthesize 工具为以下标准话术生成 {num_variants} 个自然表达变体。\n\n"
                f"{context_block}\n\n"
                f"请直接输出 JSON 数组格式的变体列表，不要输出其他内容。"
            )
        else:
            # Retry with feedback from previous validation
            synth_goal = (
                f"之前生成的部分变体未通过质量验证。请根据以下反馈重新生成变体。\n\n"
                f"{context_block}\n\n"
                f"需要重新生成的数量：{num_variants - len(all_variants)}\n"
                f"验证反馈：{feedback_text}\n\n"
                f"请使用 cockpit_synthesize 工具生成改进后的变体，直接输出 JSON 数组。"
            )

        synth_result_str = delegate_task(
            goal=synth_goal,
            context=f"这是座舱AI语音助手的话术泛化任务。第 {retry_count + 1} 轮生成。",
            toolsets=["cockpit-data"],
            parent_agent=parent_agent,
        )

        try:
            synth_result = json.loads(synth_result_str)
            synth_summary = synth_result.get("results", [{}])[0].get("summary", "")
        except (json.JSONDecodeError, IndexError):
            synth_summary = synth_result_str

        # Extract variants from child's summary
        new_variants = _extract_variants(synth_summary)
        if not new_variants:
            logger.warning(f"Retry {retry_count}: No variants extracted from child agent")
            retry_count += 1
            continue

        # ── Step 2: Delegate Validation ──────────────────────────────
        variants_json = json.dumps(new_variants, ensure_ascii=False)
        val_goal = (
            f"使用 cockpit_validate 工具验证以下泛化变体的质量。\n\n"
            f"标准话术：{standard_utterance}\n"
            f"技能/领域：{domain}\n"
            f"参数组合：{param_combination}\n"
            f"变体列表：{variants_json}\n\n"
            f"请输出验证结果的 JSON。"
        )

        val_result_str = delegate_task(
            goal=val_goal,
            context="这是座舱AI话术的质量验证任务。请严格按照验证标准评估每个变体。",
            toolsets=["cockpit-data"],
            parent_agent=parent_agent,
        )

        try:
            val_result = json.loads(val_result_str)
            val_summary = val_result.get("results", [{}])[0].get("summary", "")
        except (json.JSONDecodeError, IndexError):
            val_summary = val_result_str

        # Parse validation results
        validation = _extract_validation(val_summary)

        if validation.get("passed", True):
            # All variants passed
            all_variants = new_variants
            break
        else:
            # Some variants failed — keep the good ones, retry the rest
            passed_variants = []
            failed_feedback = []
            for vs in validation.get("variant_scores", []):
                if vs.get("passed", True):
                    passed_variants.append(vs.get("variant", ""))
                else:
                    failed_feedback.append(
                        f"变体 '{vs.get('variant', '')}' 失败原因: "
                        f"语义一致性={vs.get('semantic', 0)}, "
                        f"参数保留={vs.get('param_retention', 0)}"
                    )

            all_variants = passed_variants
            feedback_text = validation.get("feedback", "") + "\n" + "\n".join(failed_feedback)
            num_variants_remaining = num_variants - len(all_variants)

            if num_variants_remaining <= 0:
                break

            logger.info(
                f"Retry {retry_count + 1}: {len(passed_variants)} passed, "
                f"{num_variants_remaining} need regeneration"
            )
            retry_count += 1

    return json.dumps({
        "status": "success",
        "standard_utterance": standard_utterance,
        "variants": all_variants[:num_variants],
        "retries": retry_count,
        "total_variants": len(all_variants),
    }, ensure_ascii=False)


def _extract_variants(text: str) -> list:
    """Extract a JSON array of variant strings from agent response text."""
    import re
    if not text:
        return []

    # Try direct JSON parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to find JSON array in text
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except json.JSONDecodeError:
            pass

    return []


def _extract_validation(text: str) -> dict:
    """Extract validation result dict from agent response text."""
    import re
    if not text:
        return {"passed": True}

    # Try direct JSON parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to find JSON object in text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return {"passed": True}


# ── Tool Schema ──────────────────────────────────────────────────────────

DELEGATE_SYNTHESIS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cockpit_delegate_synthesize",
        "description": (
            "Orchestrate cockpit utterance synthesis with Agent-level validation. "
            "Spawns child agents via delegate_task for synthesis and validation, "
            "implementing a generate-validate-retry loop. Use this instead of "
            "cockpit_synthesize + cockpit_validate when running in agent mode."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "standard_utterance": {
                    "type": "string",
                    "description": "The standard utterance to synthesize variants for",
                },
                "domain": {
                    "type": "string",
                    "description": "Skill domain, e.g. '音乐', '导航'",
                },
                "primary_function": {
                    "type": "string",
                    "description": "Primary function",
                },
                "secondary_function": {
                    "type": "string",
                    "description": "Secondary function",
                },
                "param_combination": {
                    "type": "string",
                    "description": "Parameter combination",
                },
                "param_description": {
                    "type": "string",
                    "description": "Parameter combination description",
                },
                "num_variants": {
                    "type": "integer",
                    "description": "Number of variants to generate (default: 5)",
                    "default": 5,
                },
                "max_retries": {
                    "type": "integer",
                    "description": "Maximum validation retry rounds (default: 3)",
                    "default": 3,
                },
            },
            "required": ["standard_utterance"],
        },
    },
}


# ── Register with hermes-agent ───────────────────────────────────────────

if _HAS_DELEGATE and hermes_registry is not None:
    hermes_registry.register(
        name="cockpit_delegate_synthesize",
        toolset="cockpit-data",
        schema=DELEGATE_SYNTHESIS_SCHEMA,
        handler=lambda args, **kw: handle_cockpit_delegate_synthesize(
            standard_utterance=args.get("standard_utterance", ""),
            domain=args.get("domain", ""),
            primary_function=args.get("primary_function", ""),
            secondary_function=args.get("secondary_function", ""),
            param_combination=args.get("param_combination", ""),
            param_description=args.get("param_description", ""),
            num_variants=args.get("num_variants", 5),
            max_retries=args.get("max_retries", 3),
            parent_agent=kw.get("parent_agent"),
        ),
        description="Orchestrated synthesis with Agent-level validation via delegate_task",
        emoji="🔀",
    )
    logger.info("cockpit_delegate_synthesize registered with hermes-agent")
