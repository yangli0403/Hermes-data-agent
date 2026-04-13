---
name: cockpit-delegation-orchestrator
description: >
  Orchestration skill that teaches the parent agent how to coordinate
  cockpit utterance synthesis using hermes-agent's delegate_task for
  Agent-level generate-validate-retry loops.
version: 1.0.0
author: ORBIT Team
license: MIT
metadata:
  hermes:
    tags: [cockpit, delegation, orchestration, agent-loop]
    category: data-science
---

# Cockpit Delegation Orchestrator Skill

This skill teaches you how to orchestrate cockpit utterance synthesis using
**child agent delegation** instead of calling tools directly. This approach
leverages hermes-agent's `delegate_task` to achieve true Agent-level
reasoning, error recovery, and validation closed loops.

## When to Use

Use this skill when:
- Processing multiple utterances that benefit from parallel child agents
- You need robust generate-validate-retry loops with Agent-level reasoning
- Running in `--use-agent` mode with delegation enabled

## Delegation Workflow

### Single Utterance Flow

For each standard utterance, follow this 3-step delegation workflow:

#### Step 1: Delegate Synthesis to a Child Agent

```
delegate_task(
  goal="使用 cockpit_synthesize 工具为以下标准话术生成 5 个自然表达变体。
        技能/领域：{domain}
        参数组合：{param_combination}
        标准话术：{standard_utterance}
        请直接输出 JSON 数组格式的变体列表。",
  toolsets=["cockpit-data"]
)
```

The child agent will:
1. Receive the goal as its only context (no parent history)
2. Call `cockpit_synthesize` with the provided parameters
3. Return a summary containing the generated variants

#### Step 2: Delegate Validation to a Child Agent

```
delegate_task(
  goal="使用 cockpit_validate 工具验证以下泛化变体的质量。
        标准话术：{standard_utterance}
        变体列表：{variants_json}
        请输出验证结果的 JSON。",
  toolsets=["cockpit-data"]
)
```

The child agent will:
1. Call `cockpit_validate` with the variants
2. Return a structured verdict with scores and feedback

#### Step 3: Handle Results

- If **all passed**: collect the variants as final output
- If **some failed**: extract the feedback, then delegate a NEW synthesis
  task that includes the failure feedback, asking the child to regenerate
  ONLY the failed variants
- Maximum **3 retry rounds** per utterance

### Batch (Parallel) Flow

When processing multiple utterances, use `delegate_task` in batch mode
to process up to 3 utterances simultaneously:

```
delegate_task(
  tasks=[
    {
      "goal": "synthesize for utterance A...",
      "toolsets": ["cockpit-data"]
    },
    {
      "goal": "synthesize for utterance B...",
      "toolsets": ["cockpit-data"]
    },
    {
      "goal": "synthesize for utterance C...",
      "toolsets": ["cockpit-data"]
    }
  ]
)
```

After all children complete, validate each result and retry failures.

## Important Rules

1. **ALWAYS delegate** — never call `cockpit_synthesize` or `cockpit_validate`
   directly. Let child agents handle tool calls.
2. **Pass ALL context** — children have NO memory of your conversation.
   Include the standard utterance, domain, parameters, and any feedback
   in the `goal` field.
3. **Be explicit about output format** — tell children to output JSON arrays
   or JSON objects so you can parse their responses.
4. **Respect depth limits** — children cannot delegate further (max depth = 2).
5. **Track retries** — maintain a counter and stop after 3 retries per utterance.

## Alternative: cockpit_delegate_synthesize Tool

For convenience, you can also use the `cockpit_delegate_synthesize` tool which
encapsulates the entire delegation workflow in a single tool call:

```
cockpit_delegate_synthesize(
  standard_utterance="播放周杰伦的歌",
  domain="音乐",
  param_combination="播放+歌手",
  num_variants=5,
  max_retries=3
)
```

This tool internally uses `delegate_task` to spawn child agents and manage
the retry loop, returning only the final validated variants.

## Output Format

Final output should be a JSON object per utterance:

```json
{
  "标准话术": "播放周杰伦的歌",
  "泛化话术": ["帮我放周杰伦的歌", "来首周杰伦的", ...],
  "retries": 1,
  "validation_passed": true
}
```
