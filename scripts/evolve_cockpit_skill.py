#!/usr/bin/env python3
"""
Cockpit Skill Evolution Script.

This script is a thin adapter that connects our cockpit SKILL.md files to
hermes-agent-self-evolution's GEPA optimization pipeline.

It reuses:
- evolution.skills.skill_module.SkillModule (DSPy module wrapping SKILL.md)
- evolution.skills.skill_module.load_skill / find_skill / reassemble_skill
- evolution.core.dataset_builder.SyntheticDatasetBuilder (auto-generates eval data)
- evolution.core.fitness.skill_fitness_metric + LLMJudge (multi-dim scoring)
- evolution.core.constraints.ConstraintValidator (size / growth / structure checks)
- dspy.GEPA or dspy.MIPROv2 (the actual optimizer)

The only custom part is the cockpit-specific evaluation dataset, which we can
either generate synthetically or load from a golden set of utterance examples.
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── Project paths ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
DATASETS_DIR = PROJECT_ROOT / "datasets" / "cockpit"


def build_cockpit_golden_dataset(input_excel: str, output_dir: Path, limit: int = 20):
    """
    Build a golden evaluation dataset from the cockpit Excel data.

    Converts the structured utterance data into the EvalDataset format
    expected by hermes-agent-self-evolution.
    """
    import pandas as pd

    try:
        from evolution.core.dataset_builder import EvalDataset, EvalExample
    except ImportError:
        console.print("[red]hermes-agent-self-evolution not installed[/red]")
        sys.exit(1)

    df = pd.read_excel(input_excel).dropna(subset=["标准话术"]).head(limit)

    examples = []
    for _, row in df.iterrows():
        task_input = (
            f"对以下座舱语音指令进行泛化，生成5种自然表达变体：\n"
            f"领域: {row.get('技能/领域', '')}\n"
            f"功能: {row.get('一级功能', '')} / {row.get('二级功能', '')}\n"
            f"参数: {row.get('参数组合', '')}\n"
            f"标准话术: {row['标准话术']}"
        )

        expected_behavior = (
            f"应生成5个与'{row['标准话术']}'语义完全一致的变体。"
            f"变体应覆盖不同口语化程度和句式。"
            f"所有参数值必须保留。"
            f"输出为JSON数组格式。"
        )

        examples.append(EvalExample(
            task_input=task_input,
            expected_behavior=expected_behavior,
            difficulty="medium",
            category=str(row.get("技能/领域", "general")),
            source="golden",
        ))

    # Split: 50% train, 25% val, 25% holdout
    n = len(examples)
    train_end = int(n * 0.5)
    val_end = int(n * 0.75)

    dataset = EvalDataset(
        train=examples[:train_end],
        val=examples[train_end:val_end],
        holdout=examples[val_end:],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    dataset.save(output_dir)
    console.print(f"  Saved golden dataset: {len(examples)} examples to {output_dir}/")
    return dataset


def evolve_cockpit_skill(
    skill_name: str = "cockpit-utterance-synthesis",
    iterations: int = 10,
    eval_source: str = "synthetic",
    input_excel: str = None,
    optimizer_model: str = "openai/gpt-4.1",
    eval_model: str = "openai/gpt-4.1-mini",
    dry_run: bool = False,
):
    """
    Evolve a cockpit skill using hermes-agent-self-evolution.

    This function is a direct adapter to the upstream evolve() function,
    with cockpit-specific dataset handling.
    """
    try:
        import dspy
        from evolution.skills.evolve_skill import evolve as hermes_evolve
        from evolution.skills.skill_module import load_skill, find_skill
        from evolution.core.config import EvolutionConfig
    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/red]")
        console.print(
            "Install with:\n"
            "  pip install dspy\n"
            "  pip install 'hermes-agent-self-evolution @ "
            "git+https://github.com/NousResearch/hermes-agent-self-evolution.git'"
        )
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold magenta]Cockpit Skill Self-Evolution[/bold magenta]\n"
        f"Skill: {skill_name}\n"
        f"Iterations: {iterations}\n"
        f"Eval source: {eval_source}\n"
        f"Optimizer: {optimizer_model}",
        title="Evolution Config",
    ))

    # ── 1. Locate the skill ──────────────────────────────────────────────
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        console.print(f"[red]Skill not found: {skill_path}[/red]")
        sys.exit(1)

    skill = load_skill(skill_path)
    console.print(f"  Loaded: {skill_path.relative_to(PROJECT_ROOT)}")
    console.print(f"  Name: {skill['name']}")
    console.print(f"  Size: {len(skill['raw']):,} chars")

    if dry_run:
        console.print("\n[bold green]DRY RUN — setup validated successfully.[/bold green]")
        return

    # ── 2. Build evaluation dataset ──────────────────────────────────────
    dataset_path = DATASETS_DIR / skill_name

    if eval_source == "golden" and input_excel:
        console.print("\n[bold]Building golden dataset from Excel...[/bold]")
        build_cockpit_golden_dataset(input_excel, dataset_path)

    # ── 3. Delegate to hermes-agent-self-evolution ───────────────────────
    # This is the key integration point: we call the upstream evolve()
    # function, pointing it at our local skills directory.
    console.print("\n[bold cyan]Delegating to hermes-agent-self-evolution...[/bold cyan]")

    hermes_evolve(
        skill_name=skill_name,
        iterations=iterations,
        eval_source=eval_source,
        dataset_path=str(dataset_path) if dataset_path.exists() else None,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        hermes_repo=str(PROJECT_ROOT),
        dry_run=False,
    )

    console.print("\n[bold green]Evolution complete![/bold green]")
    console.print(f"Check the evolved SKILL.md at: {skill_path}")


if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--skill", "-s", default="cockpit-utterance-synthesis")
    @click.option("--iterations", "-n", default=10, type=int)
    @click.option("--eval-source", type=click.Choice(["synthetic", "golden"]), default="synthetic")
    @click.option("--input-excel", "-i", default=None)
    @click.option("--optimizer-model", default="openai/gpt-4.1")
    @click.option("--eval-model", default="openai/gpt-4.1-mini")
    @click.option("--dry-run", is_flag=True)
    def main(skill, iterations, eval_source, input_excel, optimizer_model, eval_model, dry_run):
        evolve_cockpit_skill(
            skill_name=skill,
            iterations=iterations,
            eval_source=eval_source,
            input_excel=input_excel,
            optimizer_model=optimizer_model,
            eval_model=eval_model,
            dry_run=dry_run,
        )

    main()
