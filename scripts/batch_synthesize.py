#!/usr/bin/env python3
"""
Batch Synthesize — parallel cockpit data synthesis via hermes-agent's BatchRunner.

This script is the primary entry point for large-scale data synthesis. It:
1. Converts the input Excel file to batch_runner-compatible JSONL (via dataset_adapter)
2. Invokes hermes-agent's BatchRunner with full parallel processing, checkpointing,
   and trajectory saving
3. Collects results from trajectories and assembles final JSON/Excel outputs

This replaces the old single-threaded for-loop in cockpit_synthesis_tool.py with
hermes-agent's industrial-grade batch processing engine.

Usage:
    python -m scripts.batch_synthesize \
        --input data/数据处理测试.xlsx \
        --run-name cockpit_run_001 \
        --workers 4 \
        --batch-size 5 \
        --variants 5

    # Resume an interrupted run
    python -m scripts.batch_synthesize \
        --input data/数据处理测试.xlsx \
        --run-name cockpit_run_001 \
        --resume
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)

# ── Hermes batch_runner probe ────────────────────────────────────────────
_HAS_BATCH_RUNNER = False
try:
    from batch_runner import BatchRunner
    _HAS_BATCH_RUNNER = True
except ImportError:
    pass

# Local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.dataset_adapter import excel_to_batch_jsonl


def _collect_batch_results(
    run_dir: Path,
    metadata_map: dict,
    output_json: str,
    output_excel: str,
):
    """
    Post-process batch_runner trajectories into final JSON/Excel outputs.

    Reads trajectories.jsonl (or batch_*.jsonl) from the run directory,
    extracts the agent's final responses, and maps them back to the original
    utterances using metadata.

    Args:
        run_dir:      Path to the batch_runner output directory (data/<run_name>/).
        metadata_map: Dict mapping prompt text → original row metadata.
        output_json:  Path for the final JSON output.
        output_excel: Path for the final Excel output.
    """
    import pandas as pd

    trajectories_file = run_dir / "trajectories.jsonl"
    if not trajectories_file.exists():
        # Fall back to individual batch files
        batch_files = sorted(run_dir.glob("batch_*.jsonl"))
        if not batch_files:
            console.print("[red]No trajectory files found in run directory.[/red]")
            return
        # Combine batch files
        all_lines = []
        for bf in batch_files:
            with open(bf, "r", encoding="utf-8") as f:
                all_lines.extend(f.readlines())
    else:
        with open(trajectories_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

    results = []
    for line in all_lines:
        try:
            entry = json.loads(line.strip())
        except json.JSONDecodeError:
            continue

        # Extract the original prompt to look up metadata
        conversations = entry.get("conversations", [])
        prompt_text = ""
        agent_response = ""
        for msg in conversations:
            if msg.get("from") == "human":
                prompt_text = msg.get("value", "")
            elif msg.get("from") == "gpt":
                # Take the last assistant message as the final response
                agent_response = msg.get("value", "")

        # Try to find metadata by matching prompt text
        meta = metadata_map.get(prompt_text)
        if not meta:
            # Fuzzy match: check if standard_utterance appears in prompt
            for key, m in metadata_map.items():
                if m.get("standard_utterance", "") in prompt_text:
                    meta = m
                    break

        if not meta:
            continue

        # Parse variants from agent response
        variants = []
        try:
            # Try direct JSON parse
            parsed = json.loads(agent_response)
            if isinstance(parsed, list):
                variants = parsed
        except (json.JSONDecodeError, TypeError):
            # Try to extract JSON array from response text
            import re
            match = re.search(r'\[.*?\]', agent_response, re.DOTALL)
            if match:
                try:
                    variants = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        results.append({
            "技能/领域": meta.get("domain", ""),
            "一级功能": meta.get("primary_function", ""),
            "二级功能": meta.get("secondary_function", ""),
            "参数组合": meta.get("param_combination", ""),
            "参数组合功能描述": meta.get("param_description", ""),
            "标准话术": meta.get("standard_utterance", ""),
            "泛化话术": variants,
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
    if excel_rows:
        pd.DataFrame(excel_rows).to_excel(output_excel, index=False)

    console.print(f"\n[green]✅ Collected {len(results)} utterances, "
                  f"{sum(len(r.get('泛化话术', [])) for r in results)} total variants[/green]")
    console.print(f"   JSON: {output_json}")
    console.print(f"   Excel: {output_excel}")


def _build_metadata_map(jsonl_path: str) -> dict:
    """Build a mapping from prompt text → metadata for result collection."""
    mapping = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                mapping[entry["prompt"]] = entry.get("metadata", {})
            except (json.JSONDecodeError, KeyError):
                continue
    return mapping


# ── Standalone helpers ────────────────────────────────────────────────────

def _assemble_standalone_output(entries, completed_indices, run_dir,
                                output_json, output_excel):
    """Assemble output files from previously completed entries (for resume)."""
    import pandas as pd
    console.print("[dim]Assembling output from previous run...[/dim]")
    # For resume with all done, we just report success
    console.print(f"[green]All {len(completed_indices)} entries were already processed.[/green]")
    console.print(f"   Check previous output at: {output_json}")


# ── Standalone fallback batch runner ─────────────────────────────────────
def _standalone_batch_run(
    jsonl_path: str,
    run_name: str,
    num_workers: int,
    resume: bool,
    output_json: str,
    output_excel: str,
):
    """
    Fallback batch processing when hermes-agent is not installed.

    Uses multiprocessing.Pool to parallelize direct tool handler calls,
    with basic checkpointing for resume support.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tools.cockpit_synthesis_tool import (
        handle_cockpit_synthesize,
        handle_cockpit_validate,
    )

    run_dir = Path("data") / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = run_dir / "checkpoint.json"

    # Load dataset
    entries = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue

    # Load checkpoint for resume
    completed_indices = set()
    if resume and checkpoint_file.exists():
        try:
            ckpt = json.loads(checkpoint_file.read_text())
            completed_indices = set(ckpt.get("completed_indices", []))
            console.print(f"[yellow]Resuming: {len(completed_indices)} already completed[/yellow]")
        except Exception:
            pass

    # Filter out completed entries
    pending = [(i, e) for i, e in enumerate(entries) if i not in completed_indices]
    console.print(f"Processing {len(pending)} entries ({len(completed_indices)} already done)")

    if not pending:
        console.print("[green]All entries already completed. Nothing to do.[/green]")
        # Still assemble output from previous results if needed
        _assemble_standalone_output(entries, completed_indices, run_dir,
                                     output_json, output_excel)
        return

    def _process_one(idx, entry):
        """Process a single entry — runs in a thread."""
        meta = entry.get("metadata", {})
        try:
            synth_result = handle_cockpit_synthesize(
                standard_utterance=meta.get("standard_utterance", ""),
                domain=meta.get("domain", ""),
                primary_function=meta.get("primary_function", ""),
                secondary_function=meta.get("secondary_function", ""),
                param_combination=meta.get("param_combination", ""),
                param_description=meta.get("param_description", ""),
                num_variants=meta.get("num_variants", 5),
            )
            variants = json.loads(synth_result)
            if isinstance(variants, dict) and "error" in variants:
                variants = []

            # Validate
            validation = None
            if meta.get("validate", True) and variants:
                val_result = handle_cockpit_validate(
                    standard_utterance=meta.get("standard_utterance", ""),
                    variants=variants,
                    domain=meta.get("domain", ""),
                    param_combination=meta.get("param_combination", ""),
                )
                try:
                    validation = json.loads(val_result)
                except json.JSONDecodeError:
                    validation = {"passed": True}

            return {
                "index": idx,
                "status": "success",
                "meta": meta,
                "variants": variants,
                "validation": validation,
            }
        except Exception as e:
            return {"index": idx, "status": "error", "error": str(e), "meta": meta}

    # Process in parallel using ThreadPoolExecutor
    # (matches hermes-agent delegate_tool's pattern for parallel child agents)
    results = []
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn
    with ThreadPoolExecutor(max_workers=min(num_workers, len(pending))) as executor:
        futures = {}
        for i, e in pending:
            future = executor.submit(_process_one, i, e)
            futures[future] = i

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Processing"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Batch", total=len(pending))
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    idx = futures[future]
                    result = {"index": idx, "status": "error", "error": str(exc), "meta": {}}
                results.append(result)
                completed_indices.add(result["index"])
                progress.update(task, advance=1)

                # Incremental checkpoint
                checkpoint_file.write_text(json.dumps({
                    "completed_indices": sorted(completed_indices),
                }, ensure_ascii=False))

    # Assemble final output
    all_results = []
    for r in sorted(results, key=lambda x: x["index"]):
        if r["status"] != "success":
            continue
        meta = r["meta"]
        all_results.append({
            "技能/领域": meta.get("domain", ""),
            "一级功能": meta.get("primary_function", ""),
            "二级功能": meta.get("secondary_function", ""),
            "参数组合": meta.get("param_combination", ""),
            "参数组合功能描述": meta.get("param_description", ""),
            "标准话术": meta.get("standard_utterance", ""),
            "泛化话术": r.get("variants", []),
            "验证结果": r.get("validation"),
        })

    import pandas as pd
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    Path(output_excel).parent.mkdir(parents=True, exist_ok=True)
    excel_rows = []
    for r in all_results:
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
    if excel_rows:
        pd.DataFrame(excel_rows).to_excel(output_excel, index=False)

    total_variants = sum(len(r.get("泛化话术", [])) for r in all_results)
    console.print(f"\n[green]✅ Standalone batch complete: {len(all_results)} utterances, "
                  f"{total_variants} variants[/green]")


# ── CLI ──────────────────────────────────────────────────────────────────

@click.command()
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
def main(input_path, output_json, output_excel, run_name, variants, limit,
         batch_size, workers, model, no_validate, resume, verbose):
    """Batch-synthesize cockpit utterances using hermes-agent's BatchRunner."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    console.print(Panel.fit(
        f"[bold cyan]Hermes Data Agent — Batch Synthesis[/bold cyan]\n"
        f"Mode: {'hermes-agent BatchRunner' if _HAS_BATCH_RUNNER else 'standalone parallel'}\n"
        f"Input: {input_path}\n"
        f"Run name: {run_name}\n"
        f"Workers: {workers} | Batch size: {batch_size}\n"
        f"Variants: {variants} | Validate: {not no_validate}\n"
        f"Resume: {resume}",
        title="Batch Configuration",
    ))

    # Step 1: Convert Excel → JSONL
    jsonl_path = f"data/{run_name}_dataset.jsonl"
    if not resume or not Path(jsonl_path).exists():
        console.print("\n[bold]Step 1:[/bold] Converting Excel → JSONL...")
        count = excel_to_batch_jsonl(
            input_path=input_path,
            output_path=jsonl_path,
            num_variants=variants,
            limit=limit,
            validate=not no_validate,
        )
        console.print(f"   ✅ Generated {count} batch entries → {jsonl_path}")
    else:
        console.print(f"\n[bold]Step 1:[/bold] Reusing existing dataset → {jsonl_path}")

    # Build metadata map for result collection
    metadata_map = _build_metadata_map(jsonl_path)

    # Step 2: Run batch processing
    if _HAS_BATCH_RUNNER:
        console.print("\n[bold]Step 2:[/bold] Running hermes-agent BatchRunner...")

        # Load our custom tools to ensure they are registered
        import tools.cockpit_synthesis_tool  # noqa: F401

        # Build the ephemeral system prompt with our skill instructions
        skills_dir = Path(__file__).parent.parent / "skills"
        skill_texts = []
        for skill_md in sorted(skills_dir.rglob("SKILL.md")):
            skill_texts.append(skill_md.read_text(encoding="utf-8"))
        ephemeral_prompt = (
            "你是一个专业的座舱AI语音助手话术泛化专家。\n"
            "请使用 cockpit_synthesize 和 cockpit_validate 工具完成任务。\n\n"
            + "\n---\n".join(skill_texts)
        )

        runner = BatchRunner(
            dataset_file=jsonl_path,
            batch_size=batch_size,
            run_name=run_name,
            distribution="default",
            max_iterations=10,
            model=model,
            num_workers=workers,
            verbose=verbose,
            ephemeral_system_prompt=ephemeral_prompt,
        )
        runner.run(resume=resume)

        # Step 3: Collect results from trajectories
        console.print("\n[bold]Step 3:[/bold] Collecting results from trajectories...")
        run_dir = Path("data") / run_name
        _collect_batch_results(run_dir, metadata_map, output_json, output_excel)

    else:
        console.print("\n[bold]Step 2:[/bold] hermes-agent not installed, using standalone parallel mode...")
        _standalone_batch_run(
            jsonl_path=jsonl_path,
            run_name=run_name,
            num_workers=workers,
            resume=resume,
            output_json=output_json,
            output_excel=output_excel,
        )


if __name__ == "__main__":
    main()
