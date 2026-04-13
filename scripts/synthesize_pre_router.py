#!/usr/bin/env python3
"""
CLI script to synthesize pre-router and capability triplet training data.

Usage:
    # Batch synthesize all data (default 10 variants per config)
    python scripts/synthesize_pre_router.py --seed-dir data/pre_router --output-dir output/pre_router

    # More variants
    python scripts/synthesize_pre_router.py --seed-dir data/pre_router --output-dir output/pre_router --variants 15

    # Single domain synthesis
    python scripts/synthesize_pre_router.py --mode single --domain file_system --complexity simple --num 10
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.pre_router_synthesis_tool import (
    handle_pre_router_batch_synthesize,
    handle_pre_router_synthesize,
    handle_capability_triplet_synthesize,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_batch(args):
    """Batch synthesize all pre-router and capability triplet data."""
    logger.info(f"Starting batch synthesis: seed_dir={args.seed_dir}, "
                f"output_dir={args.output_dir}, variants={args.variants}")

    result_str = handle_pre_router_batch_synthesize(
        seed_dir=args.seed_dir,
        output_dir=args.output_dir,
        variants_per_config=args.variants,
    )
    result = json.loads(result_str)

    if result.get("status") == "success":
        logger.info(f"Batch synthesis complete!")
        logger.info(f"  Pre-Router records: {result['pre_router_records']}")
        logger.info(f"  Capability Triplet records: {result['capability_triplet_records']}")
        logger.info(f"  Output directory: {result['output_dir']}")

        # Print summary statistics
        _print_stats(result)
    else:
        logger.error(f"Batch synthesis failed: {result}")
        sys.exit(1)


def cmd_single(args):
    """Synthesize data for a single configuration."""
    if args.data_type == "pre_router":
        logger.info(f"Synthesizing pre-router data: domain={args.domain}, "
                     f"complexity={args.complexity}, num={args.num}")
        result_str = handle_pre_router_synthesize(
            domain=args.domain,
            complexity=args.complexity,
            memory_gate=args.memory_gate,
            planner_gate=args.planner_gate,
            required_agents=args.agents or "",
            num_variants=args.num,
            seed_file=args.seed_file or "",
        )
    else:
        logger.info(f"Synthesizing capability triplet: capability={args.capability}, num={args.num}")
        result_str = handle_capability_triplet_synthesize(
            positive_capability=args.capability,
            domain=args.domain or "",
            num_variants=args.num,
            seed_file=args.seed_file or "",
        )

    records = json.loads(result_str)
    if isinstance(records, list):
        logger.info(f"Generated {len(records)} records")
        for r in records:
            print(json.dumps(r, ensure_ascii=False))
    else:
        logger.error(f"Synthesis failed: {records}")


def _print_stats(result: dict):
    """Print statistics about generated data."""
    for file_key, file_path in result.get("files", {}).items():
        if not file_path or not Path(file_path).exists():
            continue
        logger.info(f"\n--- {file_key} statistics ---")
        records = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        if file_key == "pre_router":
            # Count by domain
            domain_counts = {}
            complexity_counts = {}
            for r in records:
                out = r.get("output", {})
                d = out.get("domain", "unknown")
                c = out.get("complexity", "unknown")
                domain_counts[d] = domain_counts.get(d, 0) + 1
                complexity_counts[c] = complexity_counts.get(c, 0) + 1
            logger.info(f"  By domain: {json.dumps(domain_counts, ensure_ascii=False)}")
            logger.info(f"  By complexity: {json.dumps(complexity_counts, ensure_ascii=False)}")

        elif file_key == "capability_triplet":
            cap_counts = {}
            for r in records:
                cap = r.get("positive_capability", "unknown")
                cap_counts[cap] = cap_counts.get(cap, 0) + 1
            logger.info(f"  By capability: {json.dumps(cap_counts, ensure_ascii=False)}")


def main():
    parser = argparse.ArgumentParser(
        description="Synthesize pre-router and capability triplet training data"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Batch synthesize all data")
    batch_parser.add_argument("--seed-dir", required=True, help="Directory with seed JSONL files")
    batch_parser.add_argument("--output-dir", default="output/pre_router", help="Output directory")
    batch_parser.add_argument("--variants", type=int, default=10, help="Variants per config")

    # Single command
    single_parser = subparsers.add_parser("single", help="Synthesize for single config")
    single_parser.add_argument("--data-type", choices=["pre_router", "capability"],
                               default="pre_router", help="Data type to synthesize")
    single_parser.add_argument("--domain", default="general", help="Target domain")
    single_parser.add_argument("--complexity", default="simple", help="Complexity level")
    single_parser.add_argument("--memory-gate", default="NO_RETRIEVE", help="Memory gate")
    single_parser.add_argument("--planner-gate", default="DIRECT", help="Planner gate")
    single_parser.add_argument("--agents", default="", help="Comma-separated agent list")
    single_parser.add_argument("--capability", default="", help="Target capability (for triplet)")
    single_parser.add_argument("--num", type=int, default=10, help="Number of variants")
    single_parser.add_argument("--seed-file", default="", help="Path to seed JSONL file")

    args = parser.parse_args()

    if args.command == "batch":
        cmd_batch(args)
    elif args.command == "single":
        cmd_single(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
