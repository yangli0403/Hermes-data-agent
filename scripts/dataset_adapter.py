#!/usr/bin/env python3
"""
Dataset Adapter — converts cockpit Excel data to hermes-agent batch_runner JSONL.

hermes-agent's BatchRunner expects a JSONL file where each line has a "prompt"
field (and optional metadata). This module reads the standard cockpit Excel
format and emits one JSONL entry per row, with a natural-language prompt that
instructs the agent to invoke the cockpit_synthesize and cockpit_validate tools.

Usage:
    python -m scripts.dataset_adapter \
        --input data/数据处理测试.xlsx \
        --output data/cockpit_batch.jsonl \
        --variants 5

The generated JSONL can then be fed directly into:
    python -m batch_runner --dataset_file=data/cockpit_batch.jsonl ...
"""

import json
import logging
from pathlib import Path
from typing import Optional

import click
import pandas as pd

logger = logging.getLogger(__name__)


def excel_to_batch_jsonl(
    input_path: str,
    output_path: str,
    num_variants: int = 5,
    limit: Optional[int] = None,
    validate: bool = True,
) -> int:
    """
    Convert a cockpit Excel file into batch_runner-compatible JSONL.

    Each row becomes a JSONL entry with:
      - "prompt": a natural-language instruction for the agent
      - "metadata": original row data for traceability

    Args:
        input_path:   Path to the input Excel file.
        output_path:  Path for the output JSONL file.
        num_variants: Number of variants to request per utterance.
        limit:        Optional row limit (for testing).
        validate:     Whether to include validation instructions.

    Returns:
        Number of entries written.
    """
    df = pd.read_excel(input_path)
    required_cols = ["技能/领域", "一级功能", "二级功能", "参数组合", "参数组合功能描述", "标准话术"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df = df.dropna(subset=["标准话术"])
    if limit:
        df = df.head(limit)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            domain = str(row.get("技能/领域", ""))
            primary = str(row.get("一级功能", ""))
            secondary = str(row.get("二级功能", ""))
            param_combo = str(row.get("参数组合", ""))
            param_desc = str(row.get("参数组合功能描述", ""))
            standard = str(row["标准话术"])

            # Build a self-contained prompt that the agent can execute
            # using the cockpit_synthesize tool (and optionally cockpit_validate).
            prompt_parts = [
                f"请使用 cockpit_synthesize 工具对以下座舱语音指令进行泛化，生成 {num_variants} 个自然表达变体。",
                "",
                f"- 技能/领域：{domain}",
                f"- 一级功能：{primary}",
                f"- 二级功能：{secondary}",
                f"- 参数组合：{param_combo}",
                f"- 参数组合功能描述：{param_desc}",
                f"- 标准话术：{standard}",
            ]

            if validate:
                prompt_parts.extend([
                    "",
                    "生成完成后，请使用 cockpit_validate 工具验证所有变体的质量。",
                    "如果有变体未通过验证，请根据反馈重新生成未通过的变体，最多重试 3 次。",
                    "最终输出通过验证的变体列表（JSON 数组格式）。",
                ])
            else:
                prompt_parts.extend([
                    "",
                    "请直接输出生成的变体列表（JSON 数组格式）。",
                ])

            prompt = "\n".join(prompt_parts)

            entry = {
                "prompt": prompt,
                "metadata": {
                    "domain": domain,
                    "primary_function": primary,
                    "secondary_function": secondary,
                    "param_combination": param_combo,
                    "param_description": param_desc,
                    "standard_utterance": standard,
                    "num_variants": num_variants,
                    "validate": validate,
                },
            }

            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1

    logger.info(f"Wrote {count} entries to {output_path}")
    return count


# ── CLI ──────────────────────────────────────────────────────────────────

@click.command()
@click.option("--input", "-i", "input_path", required=True, help="Input Excel file")
@click.option("--output", "-o", "output_path", default="data/cockpit_batch.jsonl",
              help="Output JSONL file for batch_runner")
@click.option("--variants", "-n", default=5, type=int, help="Variants per utterance")
@click.option("--limit", "-l", default=None, type=int, help="Row limit (testing)")
@click.option("--no-validate", is_flag=True, help="Omit validation instructions")
def main(input_path, output_path, variants, limit, no_validate):
    """Convert cockpit Excel data to hermes-agent batch_runner JSONL format."""
    logging.basicConfig(level=logging.INFO)
    count = excel_to_batch_jsonl(
        input_path=input_path,
        output_path=output_path,
        num_variants=variants,
        limit=limit,
        validate=not no_validate,
    )
    click.echo(f"✅ Generated {count} batch entries → {output_path}")


if __name__ == "__main__":
    main()
