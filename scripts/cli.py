#!/usr/bin/env python3
"""
Hermes Data Agent CLI.

Thin CLI wrapper that orchestrates cockpit data synthesis by leveraging:
- hermes-agent's AIAgent for LLM conversation + tool calling
- hermes-agent's batch_runner for parallel processing + checkpointing
- hermes-agent's delegate_tool for Agent-level validation closed loops
- hermes-agent-self-evolution for SKILL.md optimization
- Local custom tools registered via tools/cockpit_synthesis_tool.py

When hermes-agent is not installed, falls back to standalone mode using
the tool handlers directly.
"""

import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()
logger = logging.getLogger(__name__)

# ── Hermes Agent integration probe ───────────────────────────────────────
_HAS_HERMES = False
_HAS_EVOLUTION = False
_HAS_BATCH_RUNNER = False
_HAS_DELEGATE = False

try:
    from run_agent import AIAgent
    from agent.skill_utils import parse_frontmatter, load_skill_files
    _HAS_HERMES = True
except ImportError:
    pass

try:
    from batch_runner import BatchRunner
    _HAS_BATCH_RUNNER = True
except ImportError:
    pass

try:
    from tools.delegate_tool import delegate_task
    _HAS_DELEGATE = True
except ImportError:
    pass

try:
    from evolution.skills.evolve_skill import evolve as hermes_evolve
    from evolution.skills.skill_module import load_skill, find_skill
    from evolution.core.config import EvolutionConfig
    _HAS_EVOLUTION = True
except ImportError:
    pass

# Always import our custom tool handlers (standalone fallback)
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.cockpit_synthesis_tool import (
    handle_cockpit_synthesize,
    handle_cockpit_validate,
    handle_cockpit_batch_synthesize,
)

# ORBIT tool handlers
from tools.orbit_seed_tool import handle_orbit_seed_generate
from tools.orbit_generalize_tool import handle_orbit_generalize, handle_orbit_batch_generalize
from tools.orbit_verify_tool import handle_orbit_verify, handle_orbit_batch_verify


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# =====================================================================
# CLI Group
# =====================================================================

@click.group()
@click.version_option(version="0.2.0")
def main():
    """Hermes Data Agent — Cockpit AI utterance synthesis powered by Hermes Agent."""
    pass


# =====================================================================
# Command: synthesize (original single-threaded mode)
# =====================================================================

@main.command()
@click.option("--input", "-i", "input_path", required=True, help="Input Excel file path")
@click.option("--output-json", "-oj", default="output/泛化结果.json", help="Output JSON path")
@click.option("--output-excel", "-oe", default="output/泛化结果.xlsx", help="Output Excel path")
@click.option("--variants", "-n", default=5, type=int, help="Variants per utterance")
@click.option("--limit", "-l", default=None, type=int, help="Limit rows (for testing)")
@click.option("--no-validate", is_flag=True, help="Skip validation step")
@click.option("--use-agent", is_flag=True, help="Use hermes-agent AIAgent instead of direct tool calls")
@click.option("--use-delegate", is_flag=True, help="Use delegate_tool for Agent-level validation loop")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def synthesize(input_path, output_json, output_excel, variants, limit,
               no_validate, use_agent, use_delegate, verbose):
    """Synthesize utterance variants from standard cockpit voice commands."""
    setup_logging(verbose)

    if use_delegate and not _HAS_DELEGATE:
        console.print("[yellow]delegate_tool not available, falling back to agent mode[/yellow]")
        use_delegate = False

    if use_delegate:
        mode = "hermes-agent + delegate_tool"
    elif use_agent and _HAS_HERMES:
        mode = "hermes-agent"
    else:
        mode = "standalone"

    console.print(Panel.fit(
        f"[bold cyan]Hermes Data Agent v0.2.0[/bold cyan]\n"
        f"Mode: {mode}\n"
        f"Input: {input_path}\n"
        f"Variants: {variants}\n"
        f"Validation: {'disabled' if no_validate else 'enabled'}\n"
        f"Delegation: {'enabled' if use_delegate else 'disabled'}",
        title="Synthesis Configuration",
    ))

    if use_delegate and _HAS_HERMES:
        _synthesize_via_delegate(input_path, output_json, output_excel, variants, limit, no_validate)
    elif use_agent and _HAS_HERMES:
        _synthesize_via_agent(input_path, output_json, output_excel, variants, limit, no_validate)
    else:
        if use_agent and not _HAS_HERMES:
            console.print("[yellow]hermes-agent not installed, falling back to standalone mode[/yellow]")
        _synthesize_standalone(input_path, output_json, output_excel, variants, limit, no_validate)


def _synthesize_via_delegate(input_path, output_json, output_excel, variants, limit, no_validate):
    """
    Use hermes-agent's delegate_tool for Agent-level generate-validate-retry loops.

    The parent agent uses delegate_task to spawn child agents for synthesis
    and validation, implementing true Agent-level reasoning and error recovery.
    This is the most advanced mode, leveraging the full power of hermes-agent.
    """
    # Import delegate synthesis tool to trigger registration
    import tools.delegate_synthesis  # noqa: F401
    import tools.cockpit_synthesis_tool  # noqa: F401

    # Load skill files
    skills_dir = Path(__file__).parent.parent / "skills"
    skill_files = []
    for skill_md in skills_dir.rglob("SKILL.md"):
        skill_files.append(str(skill_md.parent.name))

    console.print(f"Loading skills: {', '.join(skill_files)}")

    # Build the agent with delegation + cockpit-data toolsets
    agent = AIAgent(
        model="gpt-4.1-mini",
        toolsets=["cockpit-data", "delegation"],
        skills=skill_files,
    )

    # Compose the task prompt — instruct the agent to use delegation
    task = (
        f"你是座舱AI话术泛化编排器。请使用 delegate_task 工具来协调话术的生成和验证。\n\n"
        f"请读取文件 '{input_path}' 中的数据，对每条标准话术：\n"
        f"1. 使用 delegate_task 派生子 Agent 调用 cockpit_synthesize 生成 {variants} 个变体\n"
        f"2. 使用 delegate_task 派生子 Agent 调用 cockpit_validate 验证变体质量\n"
        f"3. 如果验证失败，根据反馈重新委托生成，最多重试 3 次\n\n"
        f"最终将所有结果保存为 JSON 到 '{output_json}'，Excel 到 '{output_excel}'。"
    )
    if limit:
        task += f"\n只处理前 {limit} 条数据。"
    if no_validate:
        task = task.replace("2. 使用 delegate_task", "2. 跳过验证步骤\n# ")

    console.print(f"\nSending delegation task to Hermes Agent...")
    result = agent.run_conversation(task)
    console.print(f"\n[green]Agent completed.[/green]")
    console.print(result[:500] if isinstance(result, str) else str(result)[:500])


def _synthesize_via_agent(input_path, output_json, output_excel, variants, limit, no_validate):
    """
    Use hermes-agent's AIAgent to run synthesis (without delegation).

    The agent loads our SKILL.md files as instructions and uses our registered
    tools (cockpit_synthesize, cockpit_validate, cockpit_batch_synthesize) to
    perform the work.
    """
    skills_dir = Path(__file__).parent.parent / "skills"
    skill_files = []
    for skill_md in skills_dir.rglob("SKILL.md"):
        skill_files.append(str(skill_md.parent.name))

    console.print(f"Loading skills: {', '.join(skill_files)}")

    import tools.cockpit_synthesis_tool  # noqa: F401

    agent = AIAgent(
        model="gpt-4.1-mini",
        toolsets=["cockpit-data"],
        skills=skill_files,
    )

    task = (
        f"Please use the cockpit_batch_synthesize tool to process the file at "
        f"'{input_path}'. Generate {variants} variants per utterance. "
        f"Save results to JSON at '{output_json}' and Excel at '{output_excel}'."
    )
    if limit:
        task += f" Only process the first {limit} utterances."
    if no_validate:
        task += " Skip validation."

    console.print(f"\nSending task to Hermes Agent...")
    result = agent.run_conversation(task)
    console.print(f"\n[green]Agent completed.[/green]")
    console.print(result[:500] if isinstance(result, str) else str(result)[:500])


def _synthesize_standalone(input_path, output_json, output_excel, variants, limit, no_validate):
    """
    Standalone mode: call tool handlers directly without the full agent loop.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Synthesizing...", total=None)

        result_str = handle_cockpit_batch_synthesize(
            input_path=input_path,
            output_json=output_json,
            output_excel=output_excel,
            num_variants=variants,
            validate=not no_validate,
            limit=limit,
        )

        progress.update(task, description="Done!")

    result = json.loads(result_str)

    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/red]")
        sys.exit(1)

    table = Table(title="Synthesis Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Utterances", str(result.get("total_utterances", 0)))
    table.add_row("Total Variants", str(result.get("total_variants", 0)))
    table.add_row("JSON Output", result.get("output_json", ""))
    table.add_row("Excel Output", result.get("output_excel", ""))
    console.print(table)


# =====================================================================
# Command: batch (NEW — parallel processing via hermes-agent BatchRunner)
# =====================================================================

@main.command()
@click.option("--input", "-i", "input_path", required=True, help="Input Excel file")
@click.option("--output-json", "-oj", default="output/泛化结果.json", help="Output JSON path")
@click.option("--output-excel", "-oe", default="output/泛化结果.xlsx", help="Output Excel path")
@click.option("--run-name", "-r", default="cockpit_run", help="Run name for checkpointing")
@click.option("--variants", "-n", default=5, type=int, help="Variants per utterance")
@click.option("--limit", "-l", default=None, type=int, help="Row limit (testing)")
@click.option("--batch-size", "-b", default=5, type=int, help="Prompts per batch")
@click.option("--workers", "-w", default=4, type=int, help="Parallel workers")
@click.option("--model", "-m", default="gpt-4.1-mini", help="Model name")
@click.option("--no-validate", is_flag=True, help="Skip validation instructions")
@click.option("--resume", is_flag=True, help="Resume from checkpoint")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def batch(input_path, output_json, output_excel, run_name, variants, limit,
          batch_size, workers, model, no_validate, resume, verbose):
    """Batch-synthesize using hermes-agent's BatchRunner (parallel + checkpoint)."""
    setup_logging(verbose)

    # Delegate to batch_synthesize script
    from scripts.batch_synthesize import main as batch_main

    # Build click context and invoke
    ctx = click.Context(batch_main)
    ctx.invoke(
        batch_main,
        input_path=input_path,
        output_json=output_json,
        output_excel=output_excel,
        run_name=run_name,
        variants=variants,
        limit=limit,
        batch_size=batch_size,
        workers=workers,
        model=model,
        no_validate=no_validate,
        resume=resume,
        verbose=verbose,
    )


# =====================================================================
# Command: evolve
# =====================================================================

@main.command()
@click.option("--skill", "-s", default="cockpit-utterance-synthesis",
              help="Skill name to evolve")
@click.option("--iterations", "-n", default=10, type=int, help="Evolution iterations")
@click.option("--eval-source", type=click.Choice(["synthetic", "golden"]),
              default="synthetic", help="Evaluation dataset source")
@click.option("--dataset", "-d", default=None, help="Path to golden dataset")
@click.option("--optimizer-model", default="openai/gpt-4.1", help="Optimizer model")
@click.option("--eval-model", default="openai/gpt-4.1-mini", help="Evaluation model")
@click.option("--dry-run", is_flag=True, help="Validate setup without running")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def evolve(skill, iterations, eval_source, dataset, optimizer_model,
           eval_model, dry_run, verbose):
    """Evolve a skill's SKILL.md using hermes-agent-self-evolution (DSPy + GEPA)."""
    setup_logging(verbose)

    if not _HAS_EVOLUTION:
        console.print(
            "[red]hermes-agent-self-evolution is not installed.[/red]\n"
            "Install with: pip install 'hermes-agent-self-evolution @ "
            "git+https://github.com/NousResearch/hermes-agent-self-evolution.git'"
        )
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold magenta]Skill Self-Evolution[/bold magenta]\n"
        f"Skill: {skill}\n"
        f"Iterations: {iterations}\n"
        f"Eval source: {eval_source}\n"
        f"Optimizer: {optimizer_model}\n"
        f"Eval model: {eval_model}",
        title="Evolution Configuration",
    ))

    skills_base = Path(__file__).parent.parent / "skills"

    hermes_evolve(
        skill_name=skill,
        iterations=iterations,
        eval_source=eval_source,
        dataset_path=dataset or str(Path("datasets") / "cockpit"),
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        hermes_repo=str(Path(__file__).parent.parent),
        dry_run=dry_run,
    )


# =====================================================================
# Command: orbit (NEW — Car-ORBIT-Agent pipeline)
# =====================================================================

@main.command()
@click.option("--config", "-c", "config_path", default=None,
              help="Vehicle function tree config (YAML/JSON)")
@click.option("--input", "-i", "input_path", default=None,
              help="Input Excel file (alternative to --config)")
@click.option("--output-dir", "-o", default="output/orbit",
              help="Output directory")
@click.option("--variants", "-n", default=5, type=int,
              help="Variants per seed")
@click.option("--limit", "-l", default=None, type=int,
              help="Limit seeds (for testing)")
@click.option("--model", "-m", default="gpt-4.1-mini",
              help="Generalization model")
@click.option("--skip-verify", is_flag=True,
              help="Skip cascade verification")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def orbit(config_path, input_path, output_dir, variants, limit, model,
          skip_verify, verbose):
    """Run Car-ORBIT-Agent pipeline: seed → generalize → cascade verify."""
    setup_logging(verbose)

    if not config_path and not input_path:
        console.print("[red]Error: must provide --config or --input[/red]")
        sys.exit(1)

    from core.config_loader import ConfigLoader
    from core.seed_engine import SeedEngine
    from core.generalization_engine import GeneralizationEngine
    from core.cascade_orchestrator import CascadeOrchestrator
    from core.rule_verifier import RuleVerifier
    from core.semantic_verifier import SemanticVerifier
    from core.safety_verifier import SafetyVerifier
    from core.llm_client import LLMClient
    from core.provenance_tracker import ProvenanceTracker
    from scripts.orbit_dataset_adapter import OrbitDatasetAdapter

    # ── 初始化 ──────────────────────────────────────────────────────
    config_loader = ConfigLoader()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    tracker = ProvenanceTracker(
        trace_path=str(output_path / "orbit_trace.jsonl")
    )

    console.print(Panel.fit(
        f"[bold cyan]Car-ORBIT-Agent Pipeline[/bold cyan]\n"
        f"Config: {config_path or 'N/A'}\n"
        f"Excel:  {input_path or 'N/A'}\n"
        f"Variants: {variants}\n"
        f"Model: {model}\n"
        f"Verify: {'disabled' if skip_verify else 'enabled'}\n"
        f"Output: {output_dir}",
        title="ORBIT Configuration",
    ))

    # ── 阶段1: 种子生成 ──────────────────────────────────────────────
    console.print("\n[bold]Stage 1: Seed Generation[/bold]")
    engine = SeedEngine(config_loader=config_loader)

    if config_path:
        seeds = engine.generate_from_config(config_path, max_seeds=limit or 1000)
    else:
        seeds = engine.extract_from_excel(input_path)

    if limit:
        seeds = seeds[:limit]

    for s in seeds:
        tracker.record_seed(s)

    console.print(f"  Generated [green]{len(seeds)}[/green] seeds")

    # ── 阶段2: 多维度泛化 ────────────────────────────────────────────
    console.print("\n[bold]Stage 2: Multi-Dimension Generalization[/bold]")
    llm_gen = LLMClient(model=model)
    gen_engine = GeneralizationEngine(
        llm_client=llm_gen, provenance_tracker=tracker, model=model
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generalizing...", total=len(seeds))
        gen_results = []
        for seed in seeds:
            result = gen_engine.generalize(seed, num_variants=variants)
            gen_results.append(result)
            progress.advance(task)

    total_variants = sum(len(r.variants) for r in gen_results)
    console.print(f"  Generated [green]{total_variants}[/green] variants from {len(seeds)} seeds")

    # ── 阶段3: 级联验证 ──────────────────────────────────────────────
    if not skip_verify:
        console.print("\n[bold]Stage 3: Cascade Verification[/bold]")
        llm_sem = LLMClient(model=model)
        llm_safe = LLMClient(model="gpt-4.1-nano")

        orchestrator = CascadeOrchestrator(
            rule_verifier=RuleVerifier(),
            semantic_verifier=SemanticVerifier(llm_client=llm_sem, model=model),
            safety_verifier=SafetyVerifier(llm_client=llm_safe, model="gpt-4.1-nano"),
            provenance_tracker=tracker,
        )

        all_records = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Verifying...", total=total_variants)
            for gen_result in gen_results:
                for variant in gen_result.variants:
                    ver_result = orchestrator.verify(variant, gen_result.seed)
                    record = tracker.build_record(
                        seed=gen_result.seed,
                        variant=variant,
                        gen_metadata={
                            "dimensions": gen_result.dimensions_used,
                            "model": gen_result.llm_model,
                        },
                        ver_result=ver_result.to_dict(),
                    )
                    all_records.append(record)
                    progress.advance(task)
    else:
        console.print("\n[bold]Stage 3: Verification [yellow]SKIPPED[/yellow][/bold]")
        all_records = []
        for gen_result in gen_results:
            for variant in gen_result.variants:
                record = tracker.build_record(
                    seed=gen_result.seed,
                    variant=variant,
                    gen_metadata={
                        "dimensions": gen_result.dimensions_used,
                        "model": gen_result.llm_model,
                    },
                    ver_result={
                        "overall_passed": True,
                        "confidence_score": 0.0,
                        "rule_check": {"stage": "rule", "passed": True, "score": 1.0, "reason": "skipped"},
                    },
                )
                all_records.append(record)

    # ── 阶段4: 输出 ──────────────────────────────────────────────────
    console.print("\n[bold]Stage 4: Export Results[/bold]")
    adapter = OrbitDatasetAdapter()

    json_path = adapter.to_json(all_records, str(output_path / "orbit_results.json"))
    jsonl_path = adapter.to_jsonl(all_records, str(output_path / "orbit_results.jsonl"))
    excel_path = adapter.to_excel(all_records, str(output_path / "orbit_results.xlsx"))
    tracker.save_trace()

    summary = adapter.generate_summary(all_records)

    # 结果表格
    table = Table(title="ORBIT Pipeline Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Seeds", str(len(seeds)))
    table.add_row("Total Variants", str(summary["total_records"]))
    table.add_row("Passed", str(summary["total_passed"]))
    table.add_row("Rejected", str(summary["total_rejected"]))
    table.add_row("Pass Rate", f"{summary['pass_rate']:.1%}")
    table.add_row("Avg Confidence", f"{summary['avg_confidence']:.3f}")
    table.add_row("JSON Output", json_path)
    table.add_row("JSONL Output", jsonl_path)
    table.add_row("Excel Output", excel_path)
    console.print(table)

    console.print("\n[green bold]ORBIT pipeline completed successfully![/green bold]")


# =====================================================================
# Command: info
# =====================================================================

@main.command()
def info():
    """Show system information and integration status."""
    console.print(Panel.fit(
        "[bold cyan]Hermes Data Agent v0.2.0[/bold cyan]\n"
        "Cockpit AI utterance synthesis powered by Hermes Agent",
        title="System Info",
    ))

    # Integration status
    status_table = Table(title="Integration Status")
    status_table.add_column("Component", style="cyan")
    status_table.add_column("Status", style="green")
    status_table.add_column("Source")

    status_table.add_row(
        "hermes-agent (AIAgent)",
        "[green]Available[/green]" if _HAS_HERMES else "[yellow]Not installed[/yellow]",
        "github.com/NousResearch/hermes-agent",
    )
    status_table.add_row(
        "batch_runner (BatchRunner)",
        "[green]Available[/green]" if _HAS_BATCH_RUNNER else "[yellow]Not installed[/yellow]",
        "hermes-agent/batch_runner.py",
    )
    status_table.add_row(
        "delegate_tool (delegate_task)",
        "[green]Available[/green]" if _HAS_DELEGATE else "[yellow]Not installed[/yellow]",
        "hermes-agent/tools/delegate_tool.py",
    )
    status_table.add_row(
        "self-evolution (GEPA)",
        "[green]Available[/green]" if _HAS_EVOLUTION else "[yellow]Not installed[/yellow]",
        "github.com/NousResearch/hermes-agent-self-evolution",
    )
    status_table.add_row(
        "Standalone tools",
        "[green]Available[/green]",
        "tools/cockpit_synthesis_tool.py",
    )
    console.print(status_table)

    # Skills
    skills_dir = Path(__file__).parent.parent / "skills"
    skill_table = Table(title="Registered Skills")
    skill_table.add_column("Name", style="cyan")
    skill_table.add_column("Category")
    skill_table.add_column("Description")

    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        content = skill_md.read_text(encoding="utf-8")
        name = skill_md.parent.name
        desc = ""
        if content.startswith("---"):
            for line in content.split("---")[1].split("\n"):
                if line.strip().startswith("description:"):
                    desc = line.split(":", 1)[1].strip()[:60]
        skill_table.add_row(name, "data-science", desc + "...")

    console.print(skill_table)

    # Tools
    tool_table = Table(title="Custom Tools")
    tool_table.add_column("Tool", style="cyan")
    tool_table.add_column("Toolset")
    tool_table.add_column("Description")
    tool_table.add_row("cockpit_synthesize", "cockpit-data", "Single utterance synthesis")
    tool_table.add_row("cockpit_validate", "cockpit-data", "Variant quality validation")
    tool_table.add_row("cockpit_batch_synthesize", "cockpit-data", "Batch synthesis from Excel")
    tool_table.add_row("cockpit_delegate_synthesize", "cockpit-data",
                       "Delegated synthesis with Agent-level validation")
    tool_table.add_row("orbit_seed_generate", "orbit", "ORBIT seed generation from config/Excel [NEW]")
    tool_table.add_row("orbit_generalize", "orbit", "Multi-dimension variant generalization [NEW]")
    tool_table.add_row("orbit_batch_generalize", "orbit", "Batch multi-dimension generalization [NEW]")
    tool_table.add_row("orbit_verify", "orbit", "Cascade verification (rule→semantic→safety) [NEW]")
    tool_table.add_row("orbit_batch_verify", "orbit", "Batch cascade verification [NEW]")
    console.print(tool_table)

    # Modes
    mode_table = Table(title="Execution Modes")
    mode_table.add_column("Mode", style="cyan")
    mode_table.add_column("Command")
    mode_table.add_column("Description")
    mode_table.add_row("Standalone", "synthesize -i ...", "Direct tool calls, single-threaded")
    mode_table.add_row("Agent", "synthesize --use-agent -i ...", "AIAgent loop with tool calling")
    mode_table.add_row("Delegate", "synthesize --use-delegate -i ...",
                       "Agent + delegate_task for validation [NEW]")
    mode_table.add_row("Batch", "batch -i ... -r run_name",
                       "BatchRunner parallel + checkpoint")
    mode_table.add_row("ORBIT", "orbit -c config.yaml",
                       "Car-ORBIT-Agent pipeline: seed→generalize→verify [NEW]")
    console.print(mode_table)


if __name__ == "__main__":
    main()
