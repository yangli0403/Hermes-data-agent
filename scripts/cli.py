#!/usr/bin/env python3
"""
Hermes Data Agent CLI.

Thin CLI wrapper that orchestrates cockpit data synthesis by leveraging:
- hermes-agent's AIAgent for LLM conversation + tool calling
- hermes-agent's batch_runner for parallel processing
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

try:
    from run_agent import AIAgent
    from agent.skill_utils import parse_frontmatter, load_skill_files
    _HAS_HERMES = True
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
@click.version_option(version="0.1.0")
def main():
    """Hermes Data Agent — Cockpit AI utterance synthesis powered by Hermes Agent."""
    pass


@main.command()
@click.option("--input", "-i", "input_path", required=True, help="Input Excel file path")
@click.option("--output-json", "-oj", default="output/泛化结果.json", help="Output JSON path")
@click.option("--output-excel", "-oe", default="output/泛化结果.xlsx", help="Output Excel path")
@click.option("--variants", "-n", default=5, type=int, help="Variants per utterance")
@click.option("--limit", "-l", default=None, type=int, help="Limit rows (for testing)")
@click.option("--no-validate", is_flag=True, help="Skip validation step")
@click.option("--use-agent", is_flag=True, help="Use hermes-agent AIAgent instead of direct tool calls")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def synthesize(input_path, output_json, output_excel, variants, limit,
               no_validate, use_agent, verbose):
    """Synthesize utterance variants from standard cockpit voice commands."""
    setup_logging(verbose)

    mode = "hermes-agent" if (use_agent and _HAS_HERMES) else "standalone"
    console.print(Panel.fit(
        f"[bold cyan]Hermes Data Agent v0.1.0[/bold cyan]\n"
        f"Mode: {mode}\n"
        f"Input: {input_path}\n"
        f"Variants: {variants}\n"
        f"Validation: {'disabled' if no_validate else 'enabled'}",
        title="Synthesis Configuration",
    ))

    if use_agent and _HAS_HERMES:
        _synthesize_via_agent(input_path, output_json, output_excel, variants, limit, no_validate)
    else:
        if use_agent and not _HAS_HERMES:
            console.print("[yellow]hermes-agent not installed, falling back to standalone mode[/yellow]")
        _synthesize_standalone(input_path, output_json, output_excel, variants, limit, no_validate)


def _synthesize_via_agent(input_path, output_json, output_excel, variants, limit, no_validate):
    """
    Use hermes-agent's AIAgent to run synthesis.

    The agent loads our SKILL.md files as instructions and uses our registered
    tools (cockpit_synthesize, cockpit_validate, cockpit_batch_synthesize) to
    perform the work. This gives us the full agent loop: tool calling,
    error recovery, context management, and sub-agent delegation.
    """
    # Load our skill files so the agent has them as context
    skills_dir = Path(__file__).parent.parent / "skills"
    skill_files = []
    for skill_md in skills_dir.rglob("SKILL.md"):
        skill_files.append(str(skill_md.parent.name))

    console.print(f"Loading skills: {', '.join(skill_files)}")

    # Import our tools to trigger registration
    import tools.cockpit_synthesis_tool  # noqa: F401

    # Build the agent with our custom toolset
    agent = AIAgent(
        model="gpt-4.1-mini",
        toolsets=["cockpit-data"],
        skills=skill_files,
    )

    # Compose the task prompt
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

    This is the fallback when hermes-agent is not installed, or when the user
    prefers direct execution without the agent overhead.
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

    # Point to our local skills directory
    skills_base = Path(__file__).parent.parent / "skills"

    # Use hermes-agent-self-evolution's evolve function directly
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


@main.command()
def info():
    """Show system information and integration status."""
    console.print(Panel.fit(
        "[bold cyan]Hermes Data Agent v0.1.0[/bold cyan]\n"
        "Cockpit AI utterance synthesis powered by Hermes Agent",
        title="System Info",
    ))

    # Integration status
    status_table = Table(title="Integration Status")
    status_table.add_column("Component", style="cyan")
    status_table.add_column("Status", style="green")
    status_table.add_column("Source")

    status_table.add_row(
        "hermes-agent",
        "[green]Available[/green]" if _HAS_HERMES else "[yellow]Not installed[/yellow]",
        "github.com/NousResearch/hermes-agent",
    )
    status_table.add_row(
        "self-evolution",
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
        # Quick parse frontmatter
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
    console.print(tool_table)


if __name__ == "__main__":
    main()
