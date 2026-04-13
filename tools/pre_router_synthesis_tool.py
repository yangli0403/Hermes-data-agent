#!/usr/bin/env python3
"""
Pre-Router Data Synthesis Tool — generate training data for SmartAgent4's Pre-Router model.

This tool reads seed data from pre_router_train.jsonl and capability_triplet_train.jsonl,
then uses LLM to synthesize diverse new samples while preserving correct routing labels.

Integrates with hermes-agent's ToolRegistry when available.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# ── LLM Client ──────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    return OpenAI()

def _get_model() -> str:
    return os.environ.get("SYNTH_MODEL", "gpt-4.1-mini")

# ── Domain / Capability Reference ────────────────────────────────────────

DOMAIN_AGENT_MAP = {
    "file_system": "fileAgent",
    "general": "generalAgent",
    "navigation": "navigationAgent",
    "multimedia": "multimediaAgent",
}

DOMAIN_CAPABILITIES = {
    "file_system": [
        "app_launch", "browser_control", "directory_operations",
        "duplicate_detection", "file_management", "file_organization", "file_search",
    ],
    "general": [
        "general_conversation", "information_analysis", "knowledge_qa",
        "memory_management", "result_summarization",
    ],
    "multimedia": [
        "daily_recommendation", "music_playback", "music_search", "playlist_management",
    ],
    "navigation": [
        "geocoding", "ip_location", "navigation", "poi_search",
        "route_planning", "weather_query",
    ],
}

ALL_CAPABILITIES = []
for caps in DOMAIN_CAPABILITIES.values():
    ALL_CAPABILITIES.extend(caps)


# ── Pre-Router Synthesis ─────────────────────────────────────────────────

PRE_ROUTER_SYNTH_PROMPT = """你是一个专业的对话系统训练数据合成专家。你的任务是为 SmartAgent4 的 Pre-Router 模型生成高质量的训练数据。

## 种子样本（参考风格和标签规则）
{seed_samples}

## 目标
请为以下路由配置生成 {num_variants} 条全新的、多样化的用户查询：

- **domain**: {domain}
- **complexity**: {complexity}
- **memory_gate**: {memory_gate}
- **planner_gate**: {planner_gate}
- **required_agents**: {required_agents}

## 生成规则
1. 每条查询必须是自然的中文口语表达，像真实用户会说的话
2. 查询之间要有明显的多样性（不同的词汇、句式、语气）
3. 查询的语义必须与指定的 domain 和 complexity 匹配
4. 如果 memory_gate=RETRIEVE，查询中必须包含时间/历史引用词（如"上次"、"之前"、"我常用的"）
5. 如果 complexity=complex 且 domain=cross_domain，查询必须涉及多个领域的操作
6. 如果 complexity=simple，查询应该是单一意图、可直接执行的
7. 如果 complexity=moderate，查询应该需要多个步骤但在同一领域内

## 输出格式
请直接输出一个 JSON 数组，每个元素是一个字符串（用户查询）。不要输出其他内容。
示例：["查询1", "查询2", "查询3"]
"""


def handle_pre_router_synthesize(
    domain: str,
    complexity: str,
    memory_gate: str = "NO_RETRIEVE",
    planner_gate: str = "DIRECT",
    required_agents: str = "",
    num_variants: int = 10,
    seed_file: str = "",
    **kwargs,
) -> str:
    """
    Generate new pre-router training samples for a given routing configuration.
    """
    # Parse required_agents
    if isinstance(required_agents, str):
        if required_agents:
            agents_list = [a.strip() for a in required_agents.split(",")]
        else:
            agents_list = [DOMAIN_AGENT_MAP.get(domain, "generalAgent")]
    else:
        agents_list = required_agents

    # Load seed samples for context
    seed_samples = _load_seed_samples(seed_file, domain, complexity)

    prompt = PRE_ROUTER_SYNTH_PROMPT.format(
        seed_samples=json.dumps(seed_samples, ensure_ascii=False, indent=2),
        num_variants=num_variants,
        domain=domain,
        complexity=complexity,
        memory_gate=memory_gate,
        planner_gate=planner_gate,
        required_agents=json.dumps(agents_list, ensure_ascii=False),
    )

    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=_get_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=2000,
        )
        content = resp.choices[0].message.content.strip()
        queries = _extract_json_array(content)

        # Assemble full records
        records = []
        for q in queries:
            records.append({
                "input": q,
                "output": {
                    "domain": domain,
                    "complexity": complexity,
                    "memory_gate": memory_gate,
                    "planner_gate": planner_gate,
                    "required_agents": agents_list,
                },
                "source": "hermes_data_agent_synthesis",
                "label_quality": "synthetic",
            })

        return json.dumps(records, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Pre-router synthesis failed: {e}")
        return json.dumps({"error": str(e)})


# ── Capability Triplet Synthesis ─────────────────────────────────────────

CAPABILITY_SYNTH_PROMPT = """你是一个专业的对话系统训练数据合成专家。你的任务是为 SmartAgent4 的 Capability 模型生成三元组训练数据。

## 种子样本（参考风格）
{seed_samples}

## 目标
请为以下能力生成 {num_variants} 条全新的、多样化的用户查询：

- **positive_capability**: {positive_capability}
- **domain**: {domain}
- **agent**: {agent}

## 能力说明
{capability_description}

## 生成规则
1. 每条查询必须精确匹配 positive_capability 的语义
2. 查询之间要有明显的多样性（不同的词汇、句式、场景）
3. 查询要像真实用户会说的话，包括口语化、简洁、详细等不同风格
4. 避免与种子样本过于相似，要有创新性

## 输出格式
请直接输出一个 JSON 数组，每个元素是一个字符串（用户查询）。不要输出其他内容。
"""

CAPABILITY_DESCRIPTIONS = {
    "app_launch": "打开或关闭应用程序，如启动微信、关闭QQ、打开计算器等",
    "browser_control": "控制浏览器操作，如用Chrome打开网页、搜索内容、访问URL等",
    "directory_operations": "目录级别的操作，如分析目录结构、查看磁盘空间、统计文件数量等",
    "duplicate_detection": "查找重复的文件或照片，去重操作",
    "file_management": "单个文件的打开、编辑、删除、重命名等操作",
    "file_organization": "文件的移动、整理、归档、分类等批量组织操作",
    "file_search": "搜索和查找特定文件，按名称、日期、类型等条件查找",
    "general_conversation": "日常闲聊、打招呼、简单回应等社交性对话",
    "information_analysis": "分析文档、数据、报告等信息内容",
    "knowledge_qa": "知识问答，解释概念、回答事实性问题",
    "memory_management": "记忆管理，记住用户偏好、存储个人信息",
    "result_summarization": "总结结果、生成摘要、整理报告",
    "daily_recommendation": "每日推荐，如推荐音乐、内容等",
    "music_playback": "播放音乐、控制播放（暂停、下一首等）",
    "music_search": "搜索特定音乐、歌曲、歌手",
    "playlist_management": "管理歌单、查看歌单、创建歌单",
    "geocoding": "地址与经纬度之间的转换",
    "ip_location": "查询当前位置、定位",
    "navigation": "导航到目的地、路线引导",
    "poi_search": "搜索兴趣点，如充电桩、餐厅、加油站等",
    "route_planning": "规划路线、查看路程、比较路线方案",
    "weather_query": "查询天气预报、气温、降雨等天气信息",
}


def handle_capability_triplet_synthesize(
    positive_capability: str,
    domain: str = "",
    agent: str = "",
    num_variants: int = 10,
    seed_file: str = "",
    **kwargs,
) -> str:
    """
    Generate new capability triplet training samples for a given capability.
    """
    if not domain:
        for d, caps in DOMAIN_CAPABILITIES.items():
            if positive_capability in caps:
                domain = d
                break
    if not agent:
        agent = DOMAIN_AGENT_MAP.get(domain, "generalAgent")

    # Build negative capabilities (same domain, different capability)
    domain_caps = DOMAIN_CAPABILITIES.get(domain, [])
    negative_pool = [c for c in domain_caps if c != positive_capability]
    # Add some cross-domain negatives
    cross_negatives = ["file_search", "general_conversation", "file_management"]
    for cn in cross_negatives:
        if cn != positive_capability and cn not in negative_pool:
            negative_pool.append(cn)

    seed_samples = _load_capability_seeds(seed_file, positive_capability)
    cap_desc = CAPABILITY_DESCRIPTIONS.get(positive_capability, positive_capability)

    prompt = CAPABILITY_SYNTH_PROMPT.format(
        seed_samples=json.dumps(seed_samples, ensure_ascii=False, indent=2),
        num_variants=num_variants,
        positive_capability=positive_capability,
        domain=domain,
        agent=agent,
        capability_description=cap_desc,
    )

    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=_get_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=2000,
        )
        content = resp.choices[0].message.content.strip()
        queries = _extract_json_array(content)

        records = []
        for q in queries:
            # Pick 3 negatives
            import random
            negs = random.sample(negative_pool, min(3, len(negative_pool)))
            records.append({
                "query": q,
                "positive_capability": positive_capability,
                "negative_capabilities": negs,
                "domain": domain,
                "agent": agent,
                "source": "hermes_data_agent_synthesis",
                "label_quality": "synthetic",
            })

        return json.dumps(records, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Capability triplet synthesis failed: {e}")
        return json.dumps({"error": str(e)})


# ── Batch Synthesis (all domains / all capabilities) ─────────────────────

def handle_pre_router_batch_synthesize(
    seed_dir: str,
    output_dir: str = "output",
    variants_per_config: int = 10,
    **kwargs,
) -> str:
    """
    Batch-synthesize pre-router data for ALL routing configurations found in seed data.
    Also synthesizes capability triplet data for ALL capabilities.
    """
    seed_path = Path(seed_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Pre-Router data ─────────────────────────────────────
    router_seed = seed_path / "pre_router_train.jsonl"
    if not router_seed.exists():
        return json.dumps({"error": f"Seed file not found: {router_seed}"})

    # Extract unique routing configurations from seed
    configs = _extract_routing_configs(router_seed)
    logger.info(f"Found {len(configs)} unique routing configurations")

    all_router_records = []
    for i, cfg in enumerate(configs):
        logger.info(f"[Pre-Router {i+1}/{len(configs)}] domain={cfg['domain']}, "
                     f"complexity={cfg['complexity']}, planner={cfg['planner_gate']}")
        result_str = handle_pre_router_synthesize(
            domain=cfg["domain"],
            complexity=cfg["complexity"],
            memory_gate=cfg["memory_gate"],
            planner_gate=cfg["planner_gate"],
            required_agents=",".join(cfg["required_agents"]),
            num_variants=variants_per_config,
            seed_file=str(router_seed),
        )
        try:
            records = json.loads(result_str)
            if isinstance(records, list):
                all_router_records.extend(records)
        except json.JSONDecodeError:
            pass
        time.sleep(0.5)  # Rate limiting

    # Save pre-router results
    router_out = out_path / "pre_router_synthetic.jsonl"
    with open(router_out, "w", encoding="utf-8") as f:
        for r in all_router_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ── Phase 2: Capability Triplet data ─────────────────────────────
    triplet_seed = seed_path / "capability_triplet_train.jsonl"
    all_triplet_records = []

    if triplet_seed.exists():
        all_caps = []
        for domain, caps in DOMAIN_CAPABILITIES.items():
            for cap in caps:
                all_caps.append((cap, domain))

        for i, (cap, domain) in enumerate(all_caps):
            logger.info(f"[Capability {i+1}/{len(all_caps)}] {cap} ({domain})")
            result_str = handle_capability_triplet_synthesize(
                positive_capability=cap,
                domain=domain,
                num_variants=variants_per_config,
                seed_file=str(triplet_seed),
            )
            try:
                records = json.loads(result_str)
                if isinstance(records, list):
                    all_triplet_records.extend(records)
            except json.JSONDecodeError:
                pass
            time.sleep(0.5)

        triplet_out = out_path / "capability_triplet_synthetic.jsonl"
        with open(triplet_out, "w", encoding="utf-8") as f:
            for r in all_triplet_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return json.dumps({
        "status": "success",
        "pre_router_records": len(all_router_records),
        "capability_triplet_records": len(all_triplet_records),
        "output_dir": str(out_path),
        "files": {
            "pre_router": str(router_out),
            "capability_triplet": str(out_path / "capability_triplet_synthetic.jsonl")
                if all_triplet_records else None,
        },
    }, ensure_ascii=False)


# ── Helper Functions ─────────────────────────────────────────────────────

def _extract_json_array(text: str) -> list:
    """Extract a JSON array from LLM response text."""
    if not text:
        return []
    # Try direct parse
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


def _load_seed_samples(seed_file: str, domain: str, complexity: str, max_seeds: int = 5) -> list:
    """Load relevant seed samples for context."""
    seeds = []
    if not seed_file or not Path(seed_file).exists():
        return seeds
    with open(seed_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                out = entry.get("output", {})
                if out.get("domain") == domain or out.get("complexity") == complexity:
                    seeds.append({"input": entry["input"], "output": out})
                    if len(seeds) >= max_seeds:
                        break
            except json.JSONDecodeError:
                continue
    return seeds


def _load_capability_seeds(seed_file: str, capability: str, max_seeds: int = 3) -> list:
    """Load relevant capability seed samples."""
    seeds = []
    if not seed_file or not Path(seed_file).exists():
        return seeds
    with open(seed_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("positive_capability") == capability:
                    seeds.append({"query": entry["query"], "capability": capability})
                    if len(seeds) >= max_seeds:
                        break
            except json.JSONDecodeError:
                continue
    return seeds


def _extract_routing_configs(seed_file: Path) -> list:
    """Extract unique routing configurations from seed data."""
    configs_set = set()
    configs = []
    with open(seed_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                out = entry.get("output", {})
                key = (
                    out.get("domain", ""),
                    out.get("complexity", ""),
                    out.get("memory_gate", ""),
                    out.get("planner_gate", ""),
                    tuple(sorted(out.get("required_agents", []))),
                )
                if key not in configs_set:
                    configs_set.add(key)
                    configs.append({
                        "domain": out.get("domain", ""),
                        "complexity": out.get("complexity", ""),
                        "memory_gate": out.get("memory_gate", ""),
                        "planner_gate": out.get("planner_gate", ""),
                        "required_agents": out.get("required_agents", []),
                    })
            except json.JSONDecodeError:
                continue
    return configs


# ── Hermes ToolRegistry Integration ──────────────────────────────────────

PRE_ROUTER_SYNTH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "pre_router_synthesize",
        "description": (
            "Generate synthetic pre-router training data for a given routing configuration. "
            "Produces diverse user queries that match the specified domain, complexity, "
            "memory_gate, planner_gate, and required_agents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": ["general", "file_system", "navigation", "multimedia", "cross_domain"],
                    "description": "Target domain",
                },
                "complexity": {
                    "type": "string",
                    "enum": ["simple", "moderate", "complex"],
                    "description": "Query complexity level",
                },
                "memory_gate": {
                    "type": "string",
                    "enum": ["NO_RETRIEVE", "RETRIEVE"],
                    "description": "Whether memory retrieval is needed",
                    "default": "NO_RETRIEVE",
                },
                "planner_gate": {
                    "type": "string",
                    "enum": ["DIRECT", "PLAN"],
                    "description": "Whether planning is needed",
                    "default": "DIRECT",
                },
                "required_agents": {
                    "type": "string",
                    "description": "Comma-separated list of required agents",
                },
                "num_variants": {
                    "type": "integer",
                    "description": "Number of queries to generate (default: 10)",
                    "default": 10,
                },
                "seed_file": {
                    "type": "string",
                    "description": "Path to seed JSONL file for reference",
                },
            },
            "required": ["domain", "complexity"],
        },
    },
}

CAPABILITY_TRIPLET_SYNTH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "capability_triplet_synthesize",
        "description": (
            "Generate synthetic capability triplet training data for a given capability. "
            "Produces diverse user queries that match the specified capability."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "positive_capability": {
                    "type": "string",
                    "description": "The target capability to generate queries for",
                },
                "domain": {
                    "type": "string",
                    "description": "Domain of the capability",
                },
                "num_variants": {
                    "type": "integer",
                    "description": "Number of queries to generate (default: 10)",
                    "default": 10,
                },
                "seed_file": {
                    "type": "string",
                    "description": "Path to seed JSONL file for reference",
                },
            },
            "required": ["positive_capability"],
        },
    },
}

PRE_ROUTER_BATCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "pre_router_batch_synthesize",
        "description": (
            "Batch-synthesize pre-router AND capability triplet training data "
            "for ALL routing configurations and capabilities found in seed data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "seed_dir": {
                    "type": "string",
                    "description": "Directory containing seed JSONL files",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for synthetic data",
                    "default": "output",
                },
                "variants_per_config": {
                    "type": "integer",
                    "description": "Number of variants per routing config / capability (default: 10)",
                    "default": 10,
                },
            },
            "required": ["seed_dir"],
        },
    },
}

# Register with hermes-agent if available
try:
    from tools.registry import registry as hermes_registry
    hermes_registry.register(
        name="pre_router_synthesize",
        toolset="cockpit-data",
        schema=PRE_ROUTER_SYNTH_SCHEMA,
        handler=lambda args, **kw: handle_pre_router_synthesize(**args),
        description="Synthesize pre-router training data",
        emoji="🔀",
    )
    hermes_registry.register(
        name="capability_triplet_synthesize",
        toolset="cockpit-data",
        schema=CAPABILITY_TRIPLET_SYNTH_SCHEMA,
        handler=lambda args, **kw: handle_capability_triplet_synthesize(**args),
        description="Synthesize capability triplet training data",
        emoji="🎯",
    )
    hermes_registry.register(
        name="pre_router_batch_synthesize",
        toolset="cockpit-data",
        schema=PRE_ROUTER_BATCH_SCHEMA,
        handler=lambda args, **kw: handle_pre_router_batch_synthesize(**args),
        description="Batch-synthesize all pre-router and capability data",
        emoji="📦",
    )
    logger.info("Pre-router synthesis tools registered with hermes-agent")
except ImportError:
    pass
