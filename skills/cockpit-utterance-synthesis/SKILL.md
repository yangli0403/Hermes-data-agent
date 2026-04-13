---
name: cockpit-utterance-synthesis
description: >
  Synthesize diverse natural-language utterance variants from standard cockpit AI
  voice commands. Generates training data for NLU models by producing colloquial,
  varied expressions while preserving semantic intent and parameter values.
version: 1.0.0
author: ORBIT Team
license: MIT
metadata:
  hermes:
    tags: [cockpit, nlu, data-synthesis, utterance, voice-assistant]
    category: data-science
---

# Cockpit Utterance Synthesis Skill

Generate diverse natural-language variants of standard cockpit AI voice commands
for NLU model training. This skill takes structured utterance data (domain, function,
parameters, standard utterance) and produces multiple colloquial Chinese expressions
that preserve the original intent and all parameter values.

## When to Use

Use this skill when you need to:
- Expand a small set of standard cockpit voice commands into a large training dataset
- Generate diverse Chinese colloquial expressions for a given voice command
- Produce NLU training data that covers varied sentence patterns, colloquial levels, and speech habits

## Input Format

Each utterance item is a JSON object with these fields:

| Field | Description | Example |
|-------|-------------|---------|
| `技能/领域` | Skill domain | 音乐, 导航, 空调 |
| `一级功能` | Primary function | 播放音乐 |
| `二级功能` | Secondary function | 指定歌手播放 |
| `参数组合` | Parameter combination | 播放+歌手 |
| `参数组合功能描述` | Parameter description | 播放指定歌手的音乐 |
| `标准话术` | Standard utterance(s) | 播放周杰伦的歌 |

## Synthesis Procedure

Follow these steps for each utterance item:

### Step 1: Analyze the Standard Utterance
- Identify the **core intent** (what the user wants to do)
- Extract **all parameter values** (artist names, song names, locations, numbers, etc.)
- Note the **domain context** (music, navigation, climate, etc.)

### Step 2: Generate Variants Along Multiple Dimensions
For each standard utterance, produce variants covering these diversity axes:

1. **Colloquial Level** — from formal to very casual:
   - Formal: "请播放周杰伦的歌曲"
   - Casual: "放首周杰伦的歌"
   - Very casual: "来点杰伦的"

2. **Sentence Pattern** — vary the grammatical structure:
   - Imperative: "播放周杰伦的歌"
   - Request: "帮我放周杰伦的歌"
   - Question: "能放周杰伦的歌吗"
   - Desire: "我想听周杰伦的歌"

3. **Filler Words** — add natural speech elements:
   - "嗯，放首周杰伦的歌吧"
   - "那个，帮我播放一下周杰伦"

4. **Abbreviation & Ellipsis** — natural shortening:
   - "周杰伦的歌" (omitting the verb when context is clear)

5. **Driving-Scene Adaptation** — keep it concise for in-car use

### Step 3: Validate Each Variant
Before including a variant, verify:
- ✅ Semantic intent is identical to the original
- ✅ ALL parameter values are preserved exactly (no substitution)
- ✅ Expression sounds natural as spoken Chinese
- ✅ No ambiguity that could confuse NLU

### Step 4: Output
Return a JSON array of variant strings. Do NOT include the original utterance.

## Output Format

Strict JSON array of strings:
```json
["variant_1", "variant_2", "variant_3", ...]
```

## Hard Constraints

1. **Parameter Preservation**: NEVER replace, modify, or omit parameter values.
   "播放周杰伦的歌" → ✅ "来首周杰伦的" / ❌ "来首歌"
2. **Intent Fidelity**: NEVER change the user's intent.
   "播放音乐" → ✅ "放首歌" / ❌ "暂停音乐"
3. **Conciseness**: Variants should be ≤ 20 characters when possible (driving safety).
4. **No Hallucination**: Do NOT invent parameters not present in the original.
