---
name: cockpit-utterance-validation
description: >
  Quality-gate skill that validates synthesized utterance variants against
  the original standard utterance. Checks semantic consistency, parameter
  retention, naturalness, and ambiguity. Returns structured pass/fail
  verdicts with actionable feedback for the synthesis skill to retry.
version: 1.0.0
author: ORBIT Team
license: MIT
metadata:
  hermes:
    tags: [cockpit, nlu, validation, quality-assurance]
    category: data-science
---

# Cockpit Utterance Validation Skill

Validate synthesized utterance variants for quality, ensuring they meet the
strict requirements of NLU training data for cockpit AI voice assistants.

## When to Use

Use this skill after the `cockpit-utterance-synthesis` skill has generated
variants. This skill acts as a **quality gate** in the synthesis pipeline:

```
Standard Utterance → [Synthesis Skill] → Variants → [THIS SKILL] → Validated Variants
                                                          ↓ (if failed)
                                                    Feedback → [Synthesis Skill] → Retry
```

## Validation Rubric

Score each variant on four dimensions (0.0 – 1.0):

### 1. Semantic Consistency (weight: 0.35)
- Does the variant express the **exact same intent** as the original?
- No added intents, no missing intents, no changed intent targets.
- Score 1.0: Perfect match. Score 0.0: Completely different intent.

### 2. Parameter Retention (weight: 0.35)
- Are **all** parameter values from the original preserved in the variant?
- Artist names, song names, locations, numbers, directions — all must appear.
- Score 1.0: All parameters present. Score 0.0: All parameters missing.

### 3. Naturalness (weight: 0.20)
- Does the variant sound like something a real driver would say in a car?
- No grammatical errors, no awkward phrasing, natural spoken Chinese.
- Score 1.0: Perfectly natural. Score 0.0: Completely unnatural.

### 4. Unambiguity (weight: 0.10)
- Could the variant be misinterpreted by an NLU system?
- Clear intent signal, no confusing homophones or double meanings.
- Score 1.0: Crystal clear. Score 0.0: Highly ambiguous.

## Validation Procedure

### Step 1: Extract Reference Information
From the input, identify:
- The **standard utterance** (ground truth)
- The **parameter values** to check for retention
- The **domain and function** for intent verification

### Step 2: Score Each Variant
For each variant in the list:
1. Check semantic consistency against the standard utterance
2. Verify all parameter values are present
3. Assess naturalness as spoken Chinese
4. Check for potential NLU ambiguity

### Step 3: Compute Overall Verdict
- **Pass threshold**: weighted average ≥ 0.75
- A variant with parameter_retention < 0.5 automatically FAILS regardless of other scores

### Step 4: Generate Feedback
For failed variants, provide:
- Which dimension(s) failed
- Specific issue description
- Suggested fix direction

## Output Format

```json
{
  "passed": true,
  "overall_score": 0.88,
  "variant_scores": [
    {
      "variant": "帮我放周杰伦的歌",
      "semantic": 1.0,
      "param_retention": 1.0,
      "naturalness": 0.9,
      "unambiguity": 0.9,
      "weighted_score": 0.96,
      "passed": true
    }
  ],
  "failed_variants": [],
  "feedback": "All variants passed quality checks."
}
```

## Integration Notes

This skill is designed to work in a **generate-validate-feedback loop** with
the `cockpit-utterance-synthesis` skill. When variants fail validation:
1. The feedback is fed back to the synthesis skill
2. The synthesis skill regenerates only the failed variants
3. The cycle repeats up to a configurable max_retries (default: 3)
